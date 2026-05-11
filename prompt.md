una aplicación de un mapa interactivo para poder visualizar los resultados actuales y la previsión del modelo, para ello necesitaremos lo siguiente: 
- mapa de la zona de la ciudad de Valencia, España
- elige la tecnologia adecuada para desplegar el mapa, la que creas que es mejor
- necesitamos visualizar los datos actuales y un deslizador con las previsiones hasta una semana
- los datos actuales de calidad de aire utiliza la pagina web: https://rvvcca.pica.gva.es
- como ejemplo esta es la de valencia port moll: https://rvvcca.pica.gva.es/val/estacio/46250301-valencia-port-moll-trans-ponent ... vamos a necesitar además también las siguientes: pista de silla, vivers, politecnic, avinguda de frança, moli del sol, conselleria meteo, bulevard sud, centre, port llit antic Túria y nazaret met-2 ... la ubicación de estas centralitas esta es su apartado de "fitxa" y dentro de la fitxa "ubicació" en la misma url
En estas urls debes descargar los datos de O3, NO2, PM25 (PM2.5):
- De la siguiente url los datos del tiempo: https://meteostat.net/es/station/08284?t=2026-05-07/2026-05-07 ... teniendo en cuenta que la fecha tiene que ser la del dia en curso, los datos a descargar tienen que ser: Fecha,	Hora, Velocidad_viento, Direccion_viento, Temperatura, Humedad_relativa, Presion, Precipitacion
- la predicción sera con un modelo generado en base a: [COLAB] 2 - model and prediction.ipynb