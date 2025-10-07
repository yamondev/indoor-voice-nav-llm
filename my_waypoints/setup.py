from setuptools import find_packages, setup

package_name = 'my_waypoints'

setup(
    name=package_name,
    version='0.0.0',
    packages=['my_waypoints'],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='yannick',
    maintainer_email='ymn9824@gmail.com',
    description='TODO: Package description',
    license='TODO: License declaration',
    entry_points={
        'console_scripts': [
        	'waypoint_recorder = my_waypoints.waypoint_recorder:main',
        ],
    },
)
