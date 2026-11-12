# The cramera viewer with every demo, for BinderHub (https://binder.intel4coro.de) and
# for a plain `docker run`: the recorded demo scenes, the laboratory, and the robot runs
# of runs.json live, through the Runs tab. Jupyter's server proxy serves the viewer at
# /cramera/, which is also the page the server opens by default.
#
# Built from this repository's root: docker build -f binder/Dockerfile -t cramera-binder .
FROM intel4coro/jupyter-ros2:jazzy-py3.12

ARG CRAM_REPOSITORY=https://github.com/cram2/cognitive_robot_abstract_machine.git
ARG CRAM_REF=main
ARG SCENES_REPOSITORY=https://github.com/AICOR-Solutions/solutions-cramera-scenes.git
ARG SCENES_REF=main

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
        ros-${ROS_DISTRO}-xacro \
        ros-${ROS_DISTRO}-robot-state-publisher \
        python3-colcon-common-extensions \
    && rm -rf /var/lib/apt/lists/*

# the robots and worlds the robot runs read from ROS share directories
COPY binder/ros_overlay.tsv binder/build_ros_overlay.sh /opt/cramera/overlay-sources/
RUN /opt/cramera/overlay-sources/build_ros_overlay.sh /opt/cramera/ros-overlay

# this commit of cramera, the scenes repository beside its own demo scenes, and CRAM's
# main, all installed editable by cramera's own install script; CRAM runs on the CPU here,
# so torch comes without its CUDA libraries
COPY . /opt/cramera/cramera
RUN cd /opt/cramera/cramera \
    && (git submodule update --init || \
        (rm -rf resources/private_meshes && \
         git clone --depth 1 https://github.com/sunava/private_meshes.git resources/private_meshes)) \
    && git clone --depth 1 --branch "${SCENES_REF}" "${SCENES_REPOSITORY}" demo/solutions-cramera-scenes \
    && git clone --branch "${CRAM_REF}" --recurse-submodules --shallow-submodules --depth 1 \
        "${CRAM_REPOSITORY}" /opt/cramera/cognitive_robot_abstract_machine \
    && python3 -m pip install --no-cache-dir uv \
    && UV_PYTHON=/usr/bin/python3.12 UV_PYTHON_PREFERENCE=only-system UV_TORCH_BACKEND=cpu \
       UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy \
       python3 scripts/install_stack.py --venv /opt/cramera/venv \
        --cram /opt/cramera/cognitive_robot_abstract_machine \
    && UV_CACHE_DIR=/tmp/uv-cache uv pip install --python /opt/cramera/venv/bin/python \
        pyopenssl service-identity \
    && rm -rf /tmp/uv-cache \
    && chown -R ${NB_USER}:users /opt/cramera

COPY binder/jupyter_server_proxy.json /opt/conda/etc/jupyter/jupyter_server_config.d/cramera.json

USER ${NB_USER}
WORKDIR ${HOME}
