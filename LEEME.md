# Garitas — archivo histórico de la frontera

Este repositorio guarda, cada 15 minutos, los tiempos de cruce de los ~50 puertos de la frontera México–Estados Unidos.

CBP publica esos números en una API pública, pero **solo publica el estado actual**. Cuando el número cambia, el anterior desaparece para siempre. Nadie lo está guardando. Canadá sí publica su histórico; Estados Unidos no.

Esto lo guarda. Y corre solo, gratis, aunque tu computadora esté apagada.

**→ El resultado se ve en [REPORTE.md](REPORTE.md), que se actualiza solo cada 15 minutos.**

---

# Cómo dejarlo corriendo

**No necesitas instalar nada ni abrir ninguna terminal.** Son diez minutos, todo desde el navegador.

## 1. Crea tu cuenta de GitHub

Ve a [github.com](https://github.com) y crea una cuenta si no tienes. Es gratis.

## 2. Crea el repositorio

1. Arriba a la derecha, botón **`+`** → **New repository**
2. Nombre: `garitas`
3. Escoge **Public**

   > **Importante:** en público, GitHub te da minutos ilimitados. En privado te da 2,000 al mes, y este proyecto gasta alrededor de 1,400 — cabe, pero apretado. Además, que el archivo sea público es tu mejor carta: es lo que hace que los medios y las agencias te citen. Si lo quieres privado, cambia `*/15` por `*/30` en el archivo del paso 3.

4. **No** marques ninguna casilla de abajo (README, .gitignore, licencia)
5. Botón **Create repository**

## 3. Sube los archivos

En la página que te queda, haz clic en **uploading an existing file**.

Arrastra estos tres archivos y la carpeta:

```
garita.py
LEEME.md
.gitignore
.github/          ← la carpeta completa, con todo lo que trae adentro
```

Abajo, botón verde **Commit changes**.

> **Si Windows te esconde la carpeta `.github`:** en el Explorador, pestaña **Vista** → marca **Elementos ocultos**. Y si aun así no te deja arrastrarla, ve al paso 3-B.

### Paso 3-B — solo si la carpeta `.github` te dio problemas

1. En tu repositorio: **Add file** → **Create new file**
2. En el nombre escribe exactamente esto, **con las diagonales**:

   ```
   .github/workflows/archivar.yml
   ```

   Al escribir cada `/`, GitHub va creando las carpetas solo.
3. Abre `archivar.yml` de los archivos que te di, copia **todo** el contenido y pégalo.
4. **Commit changes**

## 4. Enciéndelo

1. Pestaña **Actions** (arriba)
2. Si te pregunta, botón verde **I understand my workflows, go ahead and enable them**
3. En la izquierda haz clic en **Archivar garitas**
4. A la derecha, **Run workflow** → **Run workflow**

Espera un minuto y refresca. Debe aparecer una palomita verde. ✅

**Ya está.** De aquí en adelante captura solo, cada 15 minutos, para siempre.

## 5. Siembra la historia (una sola vez)

Sin esto tendrías que esperar meses a tener patrones. Con esto los tienes hoy.

1. Pestaña **Actions**
2. En la izquierda, **Importar histórico de SANDAG**
3. **Run workflow** → **Run workflow**

Baja **más de 28,000 promedios diarios de espera desde enero de 2023** que SANDAG publica abiertos y nadie usa. Tarda un par de minutos y solo se corre una vez.

Queda en `historico/sandag.csv`, **aparte** de tus capturas, porque es promedio diario: sirve para ver estacionalidad y patrón semanal, no para la tabla por hora.

## 6. Ver los resultados

Vuelve a la página principal de tu repositorio y abre **`REPORTE.md`**. Se actualiza solo.

Los primeros días verás pocos datos — es normal, apenas está juntando historia. **A la semana ya empieza a servir. Al mes ya vale.**

---

# Qué te va a aparecer

## `REPORTE.md` — lo que se actualiza solo

- **Ahora mismo:** cuánto hay en Otay y San Ysidro
- **Mediana por hora y día de la semana:** la tabla de 168 casillas que contesta *"¿a qué hora conviene cruzar el martes?"*
- **Mejor y peor hora**, con la diferencia en minutos
- **Comparación de toda la frontera**, los ~50 cruces ordenados
- **Regreso a Tijuana:** el sentido sur, con el pronóstico de Caltrans a +15 y +30
- **Patrón de largo plazo:** mes por mes y día por día desde 2023, del histórico de SANDAG
- **Salud del archivo:** desde cuándo llevas, cuántas capturas, qué tan confiable

## Qué cubre exactamente

**56 puertos de la frontera con México** (más los de Canadá, que van de pilón). De cada uno guarda hasta **12 series**:

| clase | carriles que captura |
|---|---|
| **Autos** | general · Ready Lane · **SENTRI/NEXUS** |
| **Peatonal** | general · Ready Lane |
| **Carga** | general · FAST |

En la región Tijuana: San Ysidro, PedWest, CBX, Otay Pasajeros, Otay Comercial, Tecate, y los dos registros de Otay Mesa POE que CBP trae en "Update Pending" (muy probablemente Otay II).

### Y también el regreso a Tijuana

CBP solo mide lo que entra a Estados Unidos. **El sentido sur lo mide Caltrans**, con sensores físicos instalados sobre el acceso a la garita (piloto de SANDAG, 95% de exactitud declarada), y lo publica en una tabla que **nadie archiva y ninguna app del ecosistema muestra**.

Este archivador lo captura también, en la misma corrida:

| ruta | qué guarda |
|---|---|
| San Ysidro sur por I-5 | actual, más pronóstico a +15 y +30 min |
| San Ysidro sur por I-805 | igual |
| Otay Mesa sur por SR-905 | igual |
| Tecate sur por SR-94 | cuando Caltrans lo reporta |

Guardar también los pronósticos de Caltrans tiene una razón: en unos meses vas a poder medirle la puntería, y eso es un dato que no tiene nadie.

Si Caltrans se cae o cambia su página, **la captura del norte no se ve afectada**: se anota el aviso y sigue. Puedes apagar el sur con `--sin-sur`.

**Un hueco que queda:** varios puertos traen "Update Pending" de forma permanente porque CBP no tiene sensores ni personal en todos. Se archivan igual, y el día que empiecen a reportar ya los estás capturando.

## `datos/2026-08.csv` — el archivo de verdad

Un archivo por mes. **Lo puedes abrir directo en Excel.** Un renglón cada vez que un cruce cambió de tiempo:

| columna | qué es |
|---|---|
| `capturado_utc` | cuándo lo capturaste tú — es el reloj confiable |
| `hora_cbp` | lo que CBP dice que es su hora, tal cual |
| `puerto`, `puerto_nombre`, `frontera` | de dónde |
| `clase` | pasajeros, peatones o carga |
| `carril` | general, sentri, ready o fast |
| `minutos` | la espera |
| `carriles_abiertos` | cuántos carriles había abiertos |
| `sentido` | **norte** (CBP) o **sur** (Caltrans) |

Para bajarlo todo: botón verde **Code** → **Download ZIP**.

## `bitacora.csv` y `estado.json`

La bitácora registra cada intento, con duración y errores. Sirve para demostrar que tu archivo es continuo cuando alguien te pregunte qué tan confiable es. El `estado.json` es lo último visto de cada cruce; así solo se guardan los cambios y no se repite el mismo dato 96 veces al día.

---

# Cosas que van a pasar y no son errores

**Las corridas se atrasan a veces.** GitHub no garantiza el minuto exacto en los planes gratuitos; a veces se retrasa 5 o 20 minutos. No importa: CBP actualiza como cada hora, así que igual capturas todos los cambios.

**A veces dice "Sin cambios que guardar".** Correcto. Si CBP no actualizó, no hay nada nuevo. Por eso el archivo crece poquito.

**Si dejas el repositorio 60 días sin tocarlo, GitHub pausa el cron.** Es política de ellos. Entra una vez al mes, pestaña **Actions** → **Run workflow**, y se reactiva.

**Si una captura falla, no truena nada.** El error se anota en `bitacora.csv` y sigue en la siguiente. Por eso el porcentaje de éxito aparece en el reporte.

---

# Tres cosas que hay que tener claras

**1. Esto guarda lo que CBP *dice*, no lo que de verdad pasa.** Ya se sabe que el número oficial se queda corto — es la queja de todas las reseñas de las apps de garita. Lo que este archivo te da es **la forma**: los patrones por hora, día y temporada, que son reales aunque el nivel esté mal. **El nivel** lo calibras después, midiendo cruces reales con usuarios. Forma más nivel es la predicción que nadie tiene.

**2. La API no está documentada oficialmente.** Funciona y es de dominio público, pero puede cambiar sin aviso. Por eso nunca truena: registra el error y sigue. Échale un ojo al reporte de vez en cuando.

**3. Archivar toda la frontera cuesta lo mismo que archivar uno.** Por eso guarda los ~50 cruces, incluida la frontera con Canadá. Un archivo nacional vale mucho más que uno de Tijuana, y el costo extra es cero.

---

# Si algún día quieres correrlo en tu compu

No hace falta, pero si quieres probar:

```
python garita.py capturar    una lectura de los dos sentidos
python garita.py importar    siembra el histórico de SANDAG
python garita.py reporte     regenera REPORTE.md
python garita.py predecir    cuánto esperar un día y hora dados
python garita.py estado      qué hay ahora mismo
```

Necesitas Python 3.9 o más nuevo, de [python.org](https://www.python.org/downloads/). Al instalarlo en Windows, **marca la casilla "Add Python to PATH"** en la primera pantalla.

`prueba.py` verifica que todo funcione con datos falsos, sin tocar internet. Corre `python prueba.py` si le mueves al código.

---

*Datos de la API pública de CBP (`bwt.cbp.gov/api/waittimes`). Este repositorio existe porque ese histórico no lo guarda nadie más.*
