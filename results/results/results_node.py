#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
results_node.py — ROS 2 node that BOTH logs live metrics and builds
tables/figures for your Results chapter (TTS, Intent Accuracy, Goal Success, SUS).

- Live logging (CSV): subscribes /llm_input_audio_to_text, /llm_feedback_to_user, /plan, /amcl_pose, /current_goal
- Analysis (tables+figures): computes KPIs + saves PNGs/CSVs + a compact results.md
- Optional: reads intent annotations (intent_csv) and SUS raw answers (sus_csv)

Params (declare via --ros-args -p):
  output_dir:         "./metrics_out"   # where live CSV logs are written
  analysis_out:       "./analysis_out"  # where tables/*.csv & figures/*.png go
  arrival_threshold:  0.4               # meters to declare goal reached
  max_request_window_s: 20.0            # window linking user end -> first TTS
  auto_analyze_every_s: 0.0             # if >0, run full analysis periodically
  intent_csv:         ""                # CSV with truth/pred for intents (optional)
  with_destination:   True              # compute destination exact-match when navigate_to
  sus_csv:            ""                # CSV with SUS answers (optional)

Service:
  /results_node/force_analyze  (std_srvs/Trigger) → runs analysis now

Author: ChatGPT (merged, for Yannick) | License: MIT
"""
import os
import csv
import json
import math
import time
from collections import deque
from typing import Optional

# ROS 2
import rclpy
from rclpy.node import Node
from rclpy.time import Time
from std_msgs.msg import String
from geometry_msgs.msg import PoseWithCovarianceStamped, PoseStamped
from nav_msgs.msg import Path
from std_srvs.srv import Trigger

# Analysis
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


class ResultsNode(Node):
    # ---------------------- Init & Params ----------------------
    def __init__(self):
        super().__init__('results_node')

        # Parameters (paths)
        self.declare_parameter('output_dir', './metrics_out')
        self.declare_parameter('analysis_out', './analysis_out')
        # Live metrics behavior
        self.declare_parameter('arrival_threshold', 0.4)
        self.declare_parameter('max_request_window_s', 20.0)
        # Periodic analysis
        self.declare_parameter('auto_analyze_every_s', 0.0)
        # External evaluation files
        self.declare_parameter('intent_csv', '')
        self.declare_parameter('with_destination', True)
        self.declare_parameter('sus_csv', '')

        self.out_dir = self.get_parameter('output_dir').get_parameter_value().string_value
        self.analysis_out = self.get_parameter('analysis_out').get_parameter_value().string_value
        self.arrival_threshold = float(self.get_parameter('arrival_threshold').value)
        self.max_window = float(self.get_parameter('max_request_window_s').value)
        self.auto_every = float(self.get_parameter('auto_analyze_every_s').value)
        self.intent_csv = self.get_parameter('intent_csv').get_parameter_value().string_value
        self.with_destination = bool(self.get_parameter('with_destination').value)
        self.sus_csv = self.get_parameter('sus_csv').get_parameter_value().string_value

        os.makedirs(self.out_dir, exist_ok=True)
        os.makedirs(self.analysis_out, exist_ok=True)
        self.fig_dir = os.path.join(self.analysis_out, 'figures')
        self.tbl_dir = os.path.join(self.analysis_out, 'tables')
        os.makedirs(self.fig_dir, exist_ok=True)
        os.makedirs(self.tbl_dir, exist_ok=True)

        # CSV paths for live logs
        self.csv_tts = os.path.join(self.out_dir, 'tts_latency.csv')
        self.csv_plans = os.path.join(self.out_dir, 'plans.csv')
        self.csv_replans = os.path.join(self.out_dir, 'replans.csv')
        self.csv_arrivals = os.path.join(self.out_dir, 'arrivals.csv')
        self.csv_events = os.path.join(self.out_dir, 'events.csv')
        self.summary_path = os.path.join(self.out_dir, 'summary.json')

        # Initialize CSVs with headers
        self._init_csv(self.csv_tts, ['request_id','t_start','t_first_feedback','latency_s'])
        self._init_csv(self.csv_plans, ['request_id','plan_id','t_plan','length_m','num_points'])
        self._init_csv(self.csv_replans, ['request_id','replan_count'])
        self._init_csv(self.csv_arrivals, ['request_id','success','t_start','t_arrival','duration_s','dist_threshold_m'])
        self._init_csv(self.csv_events, ['timestamp','event','payload_json'])

        # Live state (same spirit as metrics_recorder)
        self.request_counter = 0
        self.current_request_id: Optional[str] = None
        self.request_queue = deque()               # (rid, t_start)
        self.first_feedback_logged = {}            # rid -> bool
        self.plan_id_counter = 0
        self.latest_plan = None
        self.latest_plan_request = None
        self.replan_counts = {}                    # rid -> int
        self.goal_pose = None                      # last point of /plan or /current_goal
        self.request_start_times = {}              # rid -> t_start
        self.arrival_logged = set()                # closed rids

        # Subscriptions
        self.create_subscription(String, '/llm_input_audio_to_text', self.cb_input, 10)
        self.create_subscription(String, '/llm_feedback_to_user', self.cb_feedback, 10)
        self.create_subscription(Path, '/plan', self.cb_plan, 10)
        self.create_subscription(PoseWithCovarianceStamped, '/amcl_pose', self.cb_pose, 10)
        self.create_subscription(PoseStamped, '/current_goal', self.cb_current_goal, 10)

        # Force analysis service
        self.srv = self.create_service(Trigger, 'force_analyze', self.srv_force_analyze)

        # Housekeeping & (optional) periodic analysis
        self.timer_house = self.create_timer(1.0, self._housekeeping)
        if self.auto_every > 0.0:
            self.timer_auto = self.create_timer(self.auto_every, self.run_full_analysis)
        else:
            self.timer_auto = None

        self.get_logger().info(
            f"results_node started. Live CSV → {self.out_dir} | Analysis → {self.analysis_out}"
        )

    # ---------------------- Live Logging (callbacks) ----------------------
    def cb_input(self, msg: String):
        self.request_counter += 1
        rid = f"R{self.request_counter:05d}"
        t = time.time()
        self.request_queue.append((rid, t))
        self.request_start_times[rid] = t
        self.first_feedback_logged[rid] = False
        self.replan_counts.setdefault(rid, 0)
        self.current_request_id = rid
        self.log_event('user_input', {'request_id': rid, 'text': msg.data})
        self.get_logger().info(f'New request {rid}: "{msg.data}"')

    def cb_feedback(self, msg: String):
        now = time.time()
        for rid, t_start in list(self.request_queue):
            if not self.first_feedback_logged.get(rid, False):
                latency = now - t_start
                if latency <= self.max_window:
                    self._append_csv(self.csv_tts, [rid, t_start, now, f'{latency:.3f}'])
                    self.first_feedback_logged[rid] = True
                    self.log_event('first_feedback', {'request_id': rid, 'text': msg.data, 'latency_s': latency})
                    self.get_logger().info(f'First feedback for {rid}: {latency:.3f}s')
                    break

    def cb_current_goal(self, msg: PoseStamped):
        self.goal_pose = msg.pose

    def cb_plan(self, msg: Path):
        if self.current_request_id is None and len(self.request_queue) > 0:
            self.current_request_id = self.request_queue[-1][0]
        rid = self.current_request_id or 'R00000'
        self.plan_id_counter += 1
        pid = f'P{self.plan_id_counter:05d}'
        t_plan = time.time()

        # Length (meters)
        length = 0.0
        pts = msg.poses
        for i in range(len(pts)-1):
            x1, y1 = pts[i].pose.position.x, pts[i].pose.position.y
            x2, y2 = pts[i+1].pose.position.x, pts[i+1].pose.position.y
            length += math.hypot(x2-x1, y2-y1)

        self._append_csv(self.csv_plans, [rid, pid, t_plan, f'{length:.3f}', len(pts)])
        self.replan_counts[rid] = self.replan_counts.get(rid, 0) + 1
        self._append_csv(self.csv_replans, [rid, self.replan_counts[rid]])
        if len(pts) > 0:
            self.goal_pose = pts[-1].pose

        self.latest_plan = msg
        self.latest_plan_request = rid
        self.log_event('plan_received', {'request_id': rid, 'plan_id': pid, 'length_m': length, 'num_points': len(pts)})

    def cb_pose(self, msg: PoseWithCovarianceStamped):
        if self.goal_pose is None:
            return
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y
        gx = self.goal_pose.position.x
        gy = self.goal_pose.position.y
        dist = math.hypot(gx - x, gy - y)
        if dist <= self.arrival_threshold:
            rid = self.latest_plan_request or (self.current_request_id or 'R00000')
            if rid not in self.arrival_logged and rid in self.request_start_times:
                t_start = self.request_start_times[rid]
                t_arrival = time.time()
                self._append_csv(self.csv_arrivals, [
                    rid, 1, t_start, t_arrival, f'{(t_arrival - t_start):.3f}', self.arrival_threshold
                ])
                self.arrival_logged.add(rid)
                self.log_event('arrival', {'request_id': rid, 'duration_s': (t_arrival - t_start)})
                self.get_logger().info(f'Arrival for {rid}. Duration={(t_arrival - t_start):.2f}s')

    # ---------------------- CSV helpers ----------------------
    def _init_csv(self, path, headers):
        if not os.path.exists(path):
            with open(path, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow(headers)

    def _append_csv(self, path, row):
        with open(path, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(row)

    def log_event(self, name, payload):
        ts = time.time()
        self._append_csv(self.csv_events, [ts, name, json.dumps(payload, ensure_ascii=False)])

    # ---------------------- Housekeeping ----------------------
    def _housekeeping(self):
        now = time.time()
        while self.request_queue and (now - self.request_queue[0][1] > 60.0):
            self.request_queue.popleft()

    # ---------------------- Analysis API (service) ----------------------
    def srv_force_analyze(self, req, res):
        try:
            self.run_full_analysis()
            res.success = True
            res.message = f"Analysis done → {self.analysis_out}"
        except Exception as e:
            res.success = False
            res.message = f"Analysis failed: {e}"
        return res

    # ---------------------- Analysis (merged logic) ----------------------
    def run_full_analysis(self):
        self.get_logger().info("Running full analysis…")
        kpis = {}

        # --- TTS ---
        tts = self._read_csv_safe(self.csv_tts)
        if not tts.empty:
            tts['latency_s'] = pd.to_numeric(tts['latency_s'], errors='coerce')
            kpis['tts_mean_s'] = round(tts['latency_s'].mean(), 3)
            kpis['tts_std_s'] = round(tts['latency_s'].std(ddof=1), 3)
            plt.figure()
            tts['latency_s'].hist(bins=20)
            plt.title('Time-to-Speech distribution')
            plt.xlabel('Latency (s)'); plt.ylabel('Count')
            plt.tight_layout()
            plt.savefig(os.path.join(self.fig_dir, 'tts_hist.png'))
            plt.close()

        # --- Plan length / Replans ---
        plans = self._read_csv_safe(self.csv_plans)
        replans = self._read_csv_safe(self.csv_replans)
        if not plans.empty:
            plans['length_m'] = pd.to_numeric(plans['length_m'], errors='coerce')
            kpis['plan_length_mean_m'] = round(plans['length_m'].mean(), 2)
            kpis['plan_length_median_m'] = round(plans['length_m'].median(), 2)
            plt.figure()
            plans['length_m'].plot(kind='hist', bins=20)
            plt.title('Plan length distribution (m)')
            plt.xlabel('Length (m)'); plt.ylabel('Count')
            plt.tight_layout()
            plt.savefig(os.path.join(self.fig_dir, 'plan_length_hist.png'))
            plt.close()
        if not replans.empty:
            rp = replans.groupby('request_id')['replan_count'].max().reset_index()
            kpis['replans_mean'] = round(rp['replan_count'].mean(), 2)
            plt.figure()
            rp['replan_count'].value_counts().sort_index().plot(kind='bar')
            plt.title('Replans per request (max)')
            plt.xlabel('Count'); plt.ylabel('Requests')
            plt.tight_layout()
            plt.savefig(os.path.join(self.fig_dir, 'replans_bar.png'))
            plt.close()

        # --- Arrivals (Success & Duration) ---
        arrivals = self._read_csv_safe(self.csv_arrivals)
        if not arrivals.empty:
            arrivals['duration_s'] = pd.to_numeric(arrivals['duration_s'], errors='coerce')
            success_rate = (arrivals['success'].sum() / len(arrivals)) * 100.0
            kpis['goal_success_rate_pct'] = round(success_rate, 1)
            kpis['arrival_duration_mean_s'] = round(arrivals['duration_s'].mean(), 2)
            plt.figure()
            arrivals['duration_s'].plot(kind='hist', bins=20)
            plt.title('Arrival duration distribution (s)')
            plt.xlabel('Duration (s)'); plt.ylabel('Count')
            plt.tight_layout()
            plt.savefig(os.path.join(self.fig_dir, 'arrival_duration_hist.png'))
            plt.close()

        # --- Intent Accuracy (optional external CSV) ---
        if self.intent_csv and os.path.exists(self.intent_csv):
            df = pd.read_csv(self.intent_csv)
            req_cols = ['request_id','truth_intent','pred_intent','truth_destination','pred_destination']
            for c in req_cols:
                if c not in df.columns:
                    raise ValueError(f"[intent_csv] Missing column: {c}")
            intent_correct = (df['truth_intent'].astype(str).str.strip().str.lower() ==
                              df['pred_intent'].astype(str).str.strip().str.lower())
            intent_acc = 100.0 * intent_correct.mean()
            kpis['intent_accuracy_pct'] = round(float(intent_acc), 2)

            # destination exact-match for navigate_to
            if self.with_destination:
                mask_nav = df['truth_intent'].astype(str).str.lower() == 'navigate_to'
                if mask_nav.any():
                    dest_correct = (
                        df.loc[mask_nav, 'truth_destination'].astype(str).str.strip().str.lower() ==
                        df.loc[mask_nav, 'pred_destination'].astype(str).str.strip().str.lower()
                    )
                    kpis['destination_exact_match_pct'] = round(float(100.0 * dest_correct.mean()), 2)

            # overall bar
            plt.figure()
            plt.bar(['Intent Accuracy'], [intent_acc])
            plt.ylim(0, 100)
            plt.ylabel('Accuracy (%)'); plt.title('Intent Accuracy (overall)')
            plt.tight_layout()
            plt.savefig(os.path.join(self.fig_dir, 'intent_accuracy_bar.png'))
            plt.close()

            # confusion matrix if > 1 class
            labels_true = sorted(df['truth_intent'].astype(str).str.strip().str.lower().unique())
            labels_pred = sorted(df['pred_intent'].astype(str).str.strip().str.lower().unique())
            labels = sorted(set(labels_true).union(labels_pred))
            if len(labels) > 1:
                cm = pd.crosstab(
                    df['truth_intent'].astype(str).str.strip().str.lower(),
                    df['pred_intent'].astype(str).str.strip().str.lower(),
                    rownames=['True'], colnames=['Pred'], dropna=False
                ).reindex(index=labels, columns=labels, fill_value=0)
                plt.figure()
                plt.imshow(cm.values, aspect='auto')
                plt.xticks(range(len(labels)), labels, rotation=45, ha='right')
                plt.yticks(range(len(labels)), labels)
                plt.xlabel('Predicted'); plt.ylabel('True'); plt.title('Intent Confusion Matrix')
                # annotate
                for (i, j), val in np.ndenumerate(cm.values):
                    plt.text(j, i, str(val), ha='center', va='center')
                plt.tight_layout()
                plt.savefig(os.path.join(self.fig_dir, 'intent_confusion.png'))
                plt.close()

            # Save per-class breakdown
            per_class = (df.assign(correct=intent_correct)
                           .groupby('truth_intent')['correct']
                           .mean()
                           .mul(100.0)
                           .rename('class_accuracy_pct')
                           .reset_index())
            per_class.to_csv(os.path.join(self.tbl_dir, 'intent_per_class.csv'), index=False)

        # --- SUS (optional external CSV) ---
        if self.sus_csv and os.path.exists(self.sus_csv):
            sdf = pd.read_csv(self.sus_csv)
            required = ['participant_id'] + [f'Q{i}' for i in range(1, 11)]
            for c in required:
                if c not in sdf.columns:
                    raise ValueError(f"[sus_csv] Missing column: {c}")

            def sus_score(row):
                pos = sum([row[f'Q{i}'] - 1 for i in [1,3,5,7,9]])
                neg = sum([5 - row[f'Q{i}'] for i in [2,4,6,8,10]])
                return (pos + neg) * 2.5  # 0..100

            scores = sdf.apply(sus_score, axis=1)
            n = len(scores)
            mu = float(scores.mean())
            sd = float(scores.std(ddof=1)) if n > 1 else 0.0
            t_lookup = {1:12.706, 2:4.303, 3:3.182, 4:2.776, 5:2.571, 6:2.447, 7:2.365, 8:2.306, 9:2.262, 10:2.228}
            t_crit = 1.96 if n > 30 else t_lookup.get(n-1, 2.201)
            ci = t_crit * (sd / (n ** 0.5)) if n > 1 else 0.0
            ci_low, ci_high = mu - ci, mu + ci

            kpis['sus_mean'] = round(mu, 2)
            kpis['sus_std'] = round(sd, 2)
            kpis['sus_n'] = int(n)
            kpis['sus_ci95_low'] = round(ci_low, 2)
            kpis['sus_ci95_high'] = round(ci_high, 2)

            # Figures
            plt.figure()
            plt.bar(['SUS mean'], [mu])
            plt.axhline(68, linestyle='--')
            plt.ylim(0, 100)
            plt.ylabel('Score (/100)'); plt.title('System Usability Scale (mean)')
            plt.tight_layout()
            plt.savefig(os.path.join(self.fig_dir, 'sus_bar.png'))
            plt.close()

            plt.figure()
            plt.bar(sdf['participant_id'].astype(str), scores)
            plt.ylim(0, 100)
            plt.ylabel('Score (/100)'); plt.title('SUS by participant')
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            plt.savefig(os.path.join(self.fig_dir, 'sus_scores.png'))
            plt.close()

            # Save per-participant
            pd.DataFrame({'participant_id': sdf['participant_id'], 'SUS': scores}).to_csv(
                os.path.join(self.tbl_dir, 'sus_by_participant.csv'), index=False
            )

        # --- Save KPI table + Markdown summary ---
        kpi_df = pd.DataFrame([kpis])
        kpi_df.to_csv(os.path.join(self.tbl_dir, 'kpis.csv'), index=False)

        md = ["# Auto Results Summary", "",
              "| KPI | Value |", "|-----|-------|"]
        for k, v in kpis.items():
            md.append(f"| {k} | {v} |")
        with open(os.path.join(self.analysis_out, 'results.md'), 'w', encoding='utf-8') as f:
            f.write("\n".join(md))

        self.get_logger().info(f"Analysis complete. Tables → {self.tbl_dir} | Figures → {self.fig_dir}")

    # ---------------------- Utils ----------------------
    def _read_csv_safe(self, path):
        try:
            if os.path.exists(path):
                return pd.read_csv(path)
        except Exception as e:
            self.get_logger().warn(f"Failed to read {path}: {e}")
        return pd.DataFrame()

    # ---------------------- Shutdown ----------------------
    def destroy_node(self):
        # quick live summary
        summary = {
            'tts_samples': self._count_rows(self.csv_tts) - 1,
            'plans_logged': self._count_rows(self.csv_plans) - 1,
            'arrivals_logged': self._count_rows(self.csv_arrivals) - 1,
            'replans_rows': self._count_rows(self.csv_replans) - 1,
            'generated_at': time.time(),
            'arrival_threshold_m': self.arrival_threshold,
        }
        try:
            with open(self.summary_path, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2)
            self.get_logger().info(f"Summary written to {self.summary_path}")
        except Exception as e:
            self.get_logger().warn(f"Failed to write summary: {e}")
        # run a last analysis
        try:
            self.run_full_analysis()
        except Exception as e:
            self.get_logger().warn(f"Final analysis failed: {e}")
        super().destroy_node()

    def _count_rows(self, path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return sum(1 for _ in f)
        except Exception:
            return 0


def main(args=None):
    rclpy.init(args=args)
    node = ResultsNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

