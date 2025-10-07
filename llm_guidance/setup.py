from setuptools import find_packages, setup
import os

package_name = 'llm_guidance'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', os.path.join(package_name, "guidance_context.txt"), os.path.join(package_name, "guidance_dictionnary.txt")]),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='yannick',
    maintainer_email='ymn9824@gmail.com',
    description='TODO: Package description',
    license='TODO: License declaration',
    entry_points={
        'console_scripts': [
        	'llm_guidance_node = llm_guidance.llm_guidance_node:main',
        ],
    },
)
