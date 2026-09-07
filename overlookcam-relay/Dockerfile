ARG BUILD_FROM
FROM ${BUILD_FROM}

WORKDIR /opt/overlookcam

COPY requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

COPY relay.py hosted_push.py pair.py claim.py ./
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
