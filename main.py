#importar los módulos necesarios
import tempfile
import os
import zipfile
from flask import Flask, request, redirect, send_file
from skimage import io
import base64
import glob
import numpy as np
from PIL import Image, ImageEnhance, ImageOps
import random  # <-- Añade esta importación

# Inicializa la aplicación Flask
app = Flask(__name__)

# Directorio donde se guardan las imágenes
BASE_DIR = "static/images"
if not os.path.exists(BASE_DIR):
    os.makedirs(BASE_DIR)

# Variable global para almacenar la última imagen subida
last_uploaded_image = None

# Página HTML con la funcionalidad solicitada
main_html = """
<!DOCTYPE html>
<html>
<head>
  <title>Generador de Símbolos Matemáticos</title>
  <link href="https://maxcdn.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css" rel="stylesheet">
  <style>
    #myCanvas {
      border: 2px solid black;
      background-color: #FFFFFF;
      margin-top: 20px;
    }

    .canvas-container {
      margin-top: 20px;
    }

    .btn-custom {
      margin-top: 10px;
    }

    .mensaje {
      margin-top: 20px;
      font-weight: bold;
      color: #007BFF;
    }
  </style>
  <script>
    var mousePressed = false;
    var lastX, lastY;
    var ctx;

    function InitThis() {
        ctx = document.getElementById('myCanvas').getContext("2d");
        updateSymbol();
        $('#myCanvas').mousedown(function (e) {
            mousePressed = true;
            Draw(e.pageX - $(this).offset().left, e.pageY - $(this).offset().top, false);
        });

        $('#myCanvas').mousemove(function (e) {
            if (mousePressed) {
                Draw(e.pageX - $(this).offset().left, e.pageY - $(this).offset().top, true);
            }
        });

        $('#myCanvas').mouseup(function (e) {
            mousePressed = false;
        });
        $('#myCanvas').mouseleave(function (e) {
            mousePressed = false;
        });
    }

    function Draw(x, y, isDown) {
        if (isDown) {
            ctx.beginPath();
            ctx.strokeStyle = 'black';
            ctx.lineWidth = 11;
            ctx.lineJoin = "round";
            ctx.moveTo(lastX, lastY);
            ctx.lineTo(x, y);
            ctx.closePath();
            ctx.stroke();
        }
        lastX = x; lastY = y;
    }

    function clearArea() {
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
    }

    function prepareImg() {
       var canvas = document.getElementById('myCanvas');
       document.getElementById('myImage').value = canvas.toDataURL();
    }

    function updateSymbol() {
        var selectedSymbol = document.getElementById('symbolSelect').value;
        document.getElementById('mensaje').innerHTML = 'Dibujando el operador ' + selectedSymbol;
        document.getElementById('numero').value = selectedSymbol;
    }

  </script>
</head>
<body onload="InitThis();">
  <div class="container">
    <div class="row">
      <div class="col-md-6 offset-md-3 text-center">
        <h1 class="mensaje" id="mensaje">Dibujando...</h1>
        <canvas id="myCanvas" width="200" height="200"></canvas>
        <div class="canvas-container">
          <button onclick="clearArea();" class="btn btn-primary btn-custom">Borrar</button>
          <form method="post" action="upload" onsubmit="prepareImg();" enctype="multipart/form-data">
            <input id="numero" name="numero" type="hidden" value="">
            <input id="myImage" name="myImage" type="hidden" value="">
            <input id="bt_upload" type="submit" value="Enviar" class="btn btn-success btn-custom">
          </form>
          <label for="symbolSelect">Selecciona un símbolo:</label>
          <select id="symbolSelect" onchange="updateSymbol();" class="form-control">
            <option value="Σ">Σ (Sumatoria)</option>
            <option value="E">E (Esperanza)</option>
            <option value="O">O (Conjunto vacío)</option>
            <option value="θ">θ (Ángulo)</option>
          </select>
          <br>
          <a href="/download_last" class="btn btn-warning btn-custom">Descargar Última Imagen</a>
          <a href="/download_all" class="btn btn-info btn-custom">Descargar Todas las Imágenes</a>
        </div>
      </div>
    </div>
  </div>
  <script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>
  <script src="https://maxcdn.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
</body>
</html>
"""

# Función para realizar data augmentation con múltiples transformaciones
def augment_image(image, num_augmented=1250):
    augmented_images = []

    while len(augmented_images) < num_augmented:
        # Crear una copia de la imagen original para aplicar transformación
        aug_img = image.copy()

        # Rotación aleatoria entre -45 y 45 grados
        angle = random.uniform(-45, 45)
        aug_img = aug_img.rotate(angle)

        # Escalado aleatorio entre 0.7x y 1.3x
        scale = random.uniform(0.7, 1.3)
        width, height = aug_img.size
        aug_img = aug_img.resize((int(width * scale), int(height * scale)))

        # Modificar brillo aleatorio entre 0.4x y 1.6x
        brightness_enhancer = ImageEnhance.Brightness(aug_img)
        brightness = random.uniform(0.4, 1.6)
        aug_img = brightness_enhancer.enhance(brightness)

        # Modificar contraste aleatorio entre 0.5x y 1.5x
        contrast_enhancer = ImageEnhance.Contrast(aug_img)
        contrast = random.uniform(0.5, 1.5)
        aug_img = contrast_enhancer.enhance(contrast)

        # Modificar nitidez aleatorio entre 0.5x y 1.5x
        sharpness_enhancer = ImageEnhance.Sharpness(aug_img)
        sharpness = random.uniform(0.5, 1.5)
        aug_img = sharpness_enhancer.enhance(sharpness)

        augmented_images.append(aug_img)

    return augmented_images

@app.route("/")
def main():
    """Sirve la página principal con el lienzo para dibujar."""
    return main_html

@app.route('/upload', methods=['POST'])
def upload():
    """Recibe y guarda la imagen enviada desde el navegador."""
    global last_uploaded_image
    try:
        # Obtén la imagen en base64 desde el formulario
        img_data = request.form.get('myImage').replace("data:image/png;base64,", "")
        operador = request.form.get('numero')

        # Crea el directorio correspondiente al operador
        operador_dir = os.path.join(BASE_DIR, operador)
        os.makedirs(operador_dir, exist_ok=True)

        # Guarda la imagen original
        original_path = os.path.join(operador_dir, f"{operador}_original.png")
        with open(original_path, "wb") as fh:
            fh.write(base64.b64decode(img_data))
        last_uploaded_image = original_path

        print(f"Imagen original guardada en: {original_path}")

        # Generar 1250 imágenes aumentadas para cada símbolo
        image = Image.open(original_path)
        augmented_images = augment_image(image, num_augmented=1250)
        base_name = os.path.splitext(os.path.basename(original_path))[0]

        # Guarda cada imagen aumentada en el mismo directorio
        for i, aug_image in enumerate(augmented_images):
            new_filename = f"{base_name}_aug_{i}.png"
            save_path = os.path.join(operador_dir, new_filename)
            try:
                aug_image.save(save_path)
                print(f"Guardando imagen aumentada en: {save_path}")
            except Exception as e:
                print(f"Error al guardar la imagen aumentada: {e}")

        print("Imágenes aumentadas generadas")

    except Exception as err:
        print(f"Ocurrió un error: {err}")

    # Redirige a la página principal
    return redirect("/", code=302)

@app.route('/download_last', methods=['GET'])
def download_last():
    """Permite al usuario descargar la última imagen subida."""
    global last_uploaded_image
    if last_uploaded_image:
        return send_file(last_uploaded_image, as_attachment=True)
    else:
        return "No hay imagen disponible para descargar."

@app.route('/download_all', methods=['GET'])
def download_all():
    """Permite al usuario descargar todas las imágenes generadas como un archivo ZIP."""
    zip_filename = "imagenes_generadas.zip"
    zip_filepath = os.path.join(BASE_DIR, zip_filename)

    # Crea un archivo ZIP con todas las imágenes en el directorio, organizadas por operador
    with zipfile.ZipFile(zip_filepath, "w") as zipf:
        for root, dirs, files in os.walk(BASE_DIR):
            for file in files:
                if file != zip_filename:
                    zipf.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), BASE_DIR))

    return send_file(zip_filepath, as_attachment=True)

if __name__ == "__main__":
    # Ejecuta la aplicación Flask
    app.run(debug=True)