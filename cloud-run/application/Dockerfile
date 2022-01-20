FROM eu.gcr.io/[PROJECT_ID]/cloud-run/base:[TAG]

# copy Python application and pip install packages
WORKDIR /home
COPY app .
RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# execute cmd script
CMD ./cmd.sh
