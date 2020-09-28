FROM python:3.8-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# OS setup
RUN apt-get update && \
    apt-get install -y gcc && \
    apt-get install -y git &&  \
    apt-get install -y tesseract-ocr libtesseract-dev libleptonica-dev &&  \
    apt-get install -y cron &&  \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /binfun
# Copy project
COPY . /binfun/

# Creating necessary folders
RUN mkdir logs
RUN mkdir parsed-images

# Install requirements
RUN pip install -U pip && \
    pip install -r requirements.txt

# static for admin panel
RUN python manage.py collectstatic --noinput

# Gunicorn logs
RUN mkdir /var/log/gunicorn

# Cron
COPY crontab /etc/cron.d/cron-task
RUN chmod 0644 /etc/cron.d/cron-task

EXPOSE 8100
