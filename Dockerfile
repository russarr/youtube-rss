#Создаем промежуточный образ для мульибилд(Сначала устнавливаем все пакеты, потом копируем их в основной образ)
FROM python:3.12-slim-bookworm AS builder

WORKDIR /app

COPY poetry.lock pyproject.toml ./

#Создаем readme.md без него poetry ругается
RUN touch README.md

RUN python -m pip install \
	#подавлем warning от pip, что установка идет от root
    --root-user-action=ignore \
    --no-cache-dir \
	#фиксируем версию poetry
    poetry==1.8.3 && \
	#директория .venv будет создана в папке проекта
    poetry config virtualenvs.in-project true && \
    poetry install \
	#если в проект нет dev и test групп будет ошибка, поэтому ставим флаг --only main
    #--without dev,test \
    --only main \
    --no-interaction \
    --no-ansi

#Создаем основной runtime образ
FROM python:3.12-slim-bookworm 

COPY --from=builder /app/.venv /app/.venv

#добавляем .venv в PATH, чтобы можно было запуска CMD ["python", "main.py"], иначе придется CMD ["poetry", "run", "python", "main.py"]
ENV PATH="/app/.venv/bin:$PATH"

#Копируем файлы проекта
COPY . .

CMD ["python", "./main.py"]  

