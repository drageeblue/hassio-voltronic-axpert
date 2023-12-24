ARG BUILD_FROM
FROM $BUILD_FROM

ENV LANG C.UTF-8

RUN apk add --no-cache python3
RUN apk add py3-pip
RUN apk add py3-paho-mqtt
RUN apk add py3-requests
RUN apk add py3-yaml


COPY run.sh monitor.py /

CMD ["/run.sh"]
