FROM python:slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y gcc

COPY . .

RUN gcc -O3 perlin.c -lm -o perlin
RUN cd spellfix-mirror && gcc -O3 -g -fPIC -shared spellfix.c -o spellfix.so

CMD ["python", "bot.py"]