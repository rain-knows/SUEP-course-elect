FROM python:3.11-slim-bullseye

RUN apt-get update \ 
    && apt-get install -y build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY . .

CMD ["python3", "main.py"]
