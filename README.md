## App de calidad del aire (Streamlit)

### Instalacion

```bash
pip install -r requirements.txt
```

### Ejecucion

```bash
streamlit run app.py
```

### Notas

- El modelo se carga desde `lgb_PM25_h1.pkl`.
- El scraping usa `rvvcca.pica.gva.es` y `meteostat.net` (estacion 08284).
- Si faltan estaciones o datos, la app muestra avisos y mantiene el mapa activo.
