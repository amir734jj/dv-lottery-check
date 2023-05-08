FROM python:alpine

WORKDIR /app

RUN apk add --no-cache gcc musl-dev
RUN apk add libpq-dev chromium chromium-chromedriver

RUN pip install --upgrade pip
RUN pip install selenium

ENV CHROME_BIN=/usr/bin/chromium-browser \
    CHROME_PATH=/usr/lib/chromium/

COPY . .

RUN pip install -r requirements.txt

ENTRYPOINT ["python", "main.py"]
