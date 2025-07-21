FROM python:3.11

WORKDIR /app

# Install system build dependencies
RUN apt-get update && apt-get install -y gcc python3-dev build-essential

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY templates/ ./templates/


COPY app.py .

CMD ["python", "app.py"]
