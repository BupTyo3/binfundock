FROM python:3.8-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# OS setup
RUN apt-get update && \
    apt-get install -y gcc && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /pet
# Copy project
COPY . /pet/

# Install requirements
RUN pip install -U pip && \
    pip install -r requirements.txt

# Gunicorn logs
RUN mkdir /var/log/gunicorn

EXPOSE 8000
