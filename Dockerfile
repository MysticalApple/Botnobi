FROM pypy:slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y clang build-essential ninja-build cmake

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN clang -Ofast perlin.c -lm -o perlin
RUN cd spellfix-mirror && clang -Ofast -fPIC -shared spellfix.c -o spellfix.so

CMD ["pypy", "bot.py"]
