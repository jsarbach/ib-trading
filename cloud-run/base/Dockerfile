FROM python:3.9-slim

# set environment variables
ENV TWS_INSTALL_LOG=/root/Jts/tws_install.log \
    ibcIni=/root/ibc/config.ini \
    ibcPath=/opt/ibc \
    javaPath=/opt/i4j_jres \
    twsPath=/root/Jts \
    twsSettingsPath=/root/Jts

# install dependencies
RUN  apt-get update \
  && apt-get upgrade -y \
  && apt-get install --no-install-recommends -y wget unzip xvfb libxtst6 libxrender1 python3.9-dev build-essential net-tools openjfx \
  && apt-get clean \
  && apt-get -y autoremove
#RUN apt-get install -y procps

# make dirs
RUN mkdir -p /tmp && mkdir -p ${ibcPath} && mkdir -p ${twsPath}

# download and install IB TWS, write output to file so that we can parse the TWS version number later
# "echo" to confirm installation path, "yes n" to prevent startup after installation, "|| true" to override non-zero exit code
RUN wget -q -O /tmp/ibgw.sh https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh \
  && chmod +x /tmp/ibgw.sh \
  && yes n | echo | /tmp/ibgw.sh > ${TWS_INSTALL_LOG} || true \
  && rm /tmp/ibgw.sh

# download IBC
RUN wget -q -O /tmp/IBC.zip https://github.com/IbcAlpha/IBC/releases/download/3.12.0/IBCLinux-3.12.0.zip \
  && unzip /tmp/IBC.zip -d ${ibcPath} \
  && chmod +x ${ibcPath}/*.sh ${ibcPath}/*/*.sh \
  && rm /tmp/IBC.zip

# copy IBC/Jts configs
COPY ibc/config.ini ${ibcIni}
COPY ibc/jts.ini ${twsPath}/jts.ini

# copy cmd script
WORKDIR /home
COPY cmd.sh cmd.sh
RUN chmod +x cmd.sh

# set display environment variable (must be set after TWS installation)
ENV DISPLAY=:0

CMD tail -f /dev/null
