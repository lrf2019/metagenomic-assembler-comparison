FROM ubuntu:16.04
MAINTAINER Inês Mendes <cimendes@medicina.ulisboa.pt>

RUN apt-get update && apt-get -y install build-essential \
    git \
    zlib1g-dev \
    wget \
    perl \
    bioperl

WORKDIR /NGStools

# Install velvet
RUN wget https://www.ebi.ac.uk/~zerbino/velvet/velvet_1.2.10.tgz
RUN tar xf velvet_1.2.10.tgz && rm velvet_1.2.10.tgz
RUN cd velvet_1.2.10 && make
ENV PATH="/NGStools/velvet_1.2.10:$PATH"

# Install velvetopitimiser
RUN wget https://github.com/tseemann/VelvetOptimiser/archive/2.2.6.tar.gz
RUN tar xf 2.2.6.tar.gz && rm 2.2.6.tar.gz
ENV PATH="/NGStools/VelvetOptimiser-2.2.6:$PATH"