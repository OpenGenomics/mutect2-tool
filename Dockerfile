FROM quay.io/jeremiahsavage/cdis_base

USER root
RUN apt-get update && apt-get install -y --force-yes \
    openjdk-8-jre-headless \
    libpq-dev \
    python-psycopg2

USER ubuntu
ENV HOME /home/ubuntu

ENV mutect-tool 0.8e

RUN mkdir -p ${HOME}/tools/mutect-tool
ADD docker/GenomeAnalysisTK.jar ${HOME}/tools/
ADD mutect-tool ${HOME}/tools/mutect-tool/
ADD setup.* ${HOME}/tools/mutect-tool/
ADD requirements.txt ${HOME}/tools/mutect-tool/

RUN /bin/bash -c "source ~/.virtualenvs/p3/bin/activate \
    && cd ~/tools/mutect-tool \
    && pip install -r ./requirements.txt"

WORKDIR ${HOME}