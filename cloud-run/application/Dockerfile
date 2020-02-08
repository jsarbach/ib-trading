FROM eu.gcr.io/[PROJECT_ID]/cloud-run/base:stable

# copy Python stuff and pip install packages
WORKDIR /home
COPY py .
RUN pip install -r requirements.txt

# execute cmd script to start Xvfb and gunicorn
CMD ./cmd.sh
