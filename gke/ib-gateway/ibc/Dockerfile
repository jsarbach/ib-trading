FROM ubuntu:18.04

# install dependencies
RUN  apt-get update \
  && apt-get install -y wget unzip xvfb libxtst6 libxrender1 xterm socat procps

# set environment variables
ENV APP=GATEWAY \
    IBC_INI=/root/ibc/config.ini \
    IBC_PATH=/opt/ibc \
    JAVA_PATH_ROOT=/opt/i4j_jres \
    LOG_PATH=/opt/ibc/logs \
    TWS_INSTALL_LOG=/root/Jts/tws_install.log \
    TWS_PATH=/root/Jts \
    TWS_SETTINGS_PATH=/root/Jts

# make dirs
RUN mkdir -p /tmp && mkdir -p ${IBC_PATH} && mkdir -p ${TWS_PATH}

# download IB TWS
RUN wget -q -O /tmp/ibgw.sh https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh
RUN chmod +x /tmp/ibgw.sh

# download IBC
RUN wget -q -O /tmp/IBC.zip https://github.com/IbcAlpha/IBC/releases/download/3.8.1/IBCLinux-3.8.1.zip
RUN unzip /tmp/IBC.zip -d ${IBC_PATH}
RUN chmod +x ${IBC_PATH}/*.sh ${IBC_PATH}/*/*.sh

# install TWS, write output to file so that we can parse the TWS version number later
RUN yes n | /tmp/ibgw.sh > ${TWS_INSTALL_LOG}

# remove downloaded files
RUN rm /tmp/ibgw.sh /tmp/IBC.zip

# copy IBC/Jts configs
COPY config/config.ini ${IBC_INI}
COPY config/jts.ini ${TWS_PATH}/jts.ini

# copy cmd script
WORKDIR /home
COPY cmd.sh cmd.sh
RUN chmod +x cmd.sh

# set display environment variable (must be set after TWS installation)
ENV DISPLAY=:0

# execute cmd script
CMD ./cmd.sh
