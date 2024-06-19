# Use una imagen base oficial de Python
FROM python:3.9-slim

# Establezca el directorio de trabajo en /app
WORKDIR /app

# Copie el archivo de requisitos
COPY /src/requirements.txt ./

# Instale las dependencias
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copie el contenido del directorio actual en /app
COPY src .

# Especificar la entrada del contenedor
CMD ["python", "bot-binance.py"]
