# OllamaChat

OllamaChat es un cliente de escritorio accesible para hablar con modelos de
lenguaje locales (Ollama) desde Windows. Diseñado para usuarios de lectores
de pantalla como NVDA y JAWS.

## Requisitos

- Windows 10 u 11
- Python 3.10 o superior
- Ollama instalado y ejecutándose en http://localhost:11434
- Opcional: un modelo de visión como `llava` para usar imágenes

## Instalación

1. Descargá el código o cloná el repositorio:

   `git clone <url-del-repo>`
   `cd chat-llm-local`

2. Instalá las dependencias con UV:

   `uv sync`

   Si no usás UV, también podés usar pip con el archivo requirements.txt:

   `pip install -r requirements.txt`

3. Ejecutá la aplicación:

   `uv run python -m ollamachat`
   o
   `python -m ollamachat`

## Atajos de teclado

- Alt+1: foco en campo de mensaje
- Alt+2: foco en historial
- Alt+3: foco en selector de modelo
- Alt+4: foco en temperatura
- Alt+5: foco en prompt de sistema
- Alt+6: foco en usar modelo
- Ctrl+N: nueva conversación
- Ctrl+O: abrir conversación guardada
- Ctrl+S: guardar conversación actual
- F2: anunciar estado de sesión
- F5: actualizar lista de modelos
- F6: ciclar paneles
- Escape: detener generación de respuesta
- Enter: enviar mensaje
- Shift+Enter: nueva línea en el campo de entrada

## Notas para usuarios de lector de pantalla

El área de conversación es un campo de texto estándar. Con NVDA en modo
browse, podés revisar el contenido con las flechas. Los mensajes nuevos se
anuncian automáticamente a medida que llegan.

Los controles tienen nombres descriptivos accesibles mediante Tab y
Shift+Tab. Los sliders anuncian su valor al moverlos.

## Solución de problemas

- "No se puede conectar a Ollama": asegurate de que Ollama esté instalado
  y ejecutándose. Abrí una terminal y ejecutá `ollama serve` o iniciá
  Ollama desde el menú de inicio.

- No se escucha la voz: si falta el paquete accessible-output2 o no hay un
  motor TTS instalado, la aplicación funciona en modo silencioso. Instalá
  NVDA o JAWS para activar la salida de voz.

- En WSL (Subsistema de Windows para Linux) la interfaz gráfica no se puede
  ejecutar. Usá OllamaChat directamente en Windows.

## Modelos con visión

Para usar imágenes necesitás un modelo multimodal como `llava`. Instalalo
con:

`ollama pull llava`
