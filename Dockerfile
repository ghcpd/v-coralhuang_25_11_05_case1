FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

CMD ["pytest", "-q", "--tb=short", "--json-report", "--json-report-file=raw_results.json"]