FROM python

WORKDIR /app

COPY . .
RUN pip install -r requirements.txt

COPY . .

ENTRYPOINT ["python", "main.py"]
