FROM python:alpine

WORKDIR /app

RUN apk update && apk upgrade && \
    apk add --no-cache gcc musl-dev
RUN apk add --no-cache \
    nss \
    freetype \
    harfbuzz \
    ca-certificates \
    ttf-freefont
RUN apk add --no-cache \
    libexif \
    udev \
    xvfb \
    libpq-dev \
    chromium \
    chromium-chromedriver

RUN pip install --upgrade pip
RUN pip install selenium pyvirtualdisplay

ENV CHROME_BIN=/usr/bin/chromium-browser \
    CHROME_PATH=/usr/lib/chromium/

COPY . .

RUN pip install -r requirements.txt

ENTRYPOINT ["python", "main.py"]
