# HotBoat Chile — landing estática

Una sola página HTML (`index.html`) optimizada para carga rápida y SEO: metas, un `h1`, JSON-LD, sin dependencias pesadas.

## Repo aparte del backend

Este proyecto vive fuera del repositorio `hotboat-whatsapp`; solo contenido público pensado para hospedar donde quieras (WordPress FTP, nginx, GitHub Pages, Netlify, etc.).

## Publicar un remoto nuevo

Desde esta carpeta:

```bash
git init
git add .
git commit -m "Initial commit: landing HotBoat Chile"
```

Crea el repositorio vacío en GitHub/GitLab y enlázalo:

```bash
git remote add origin git@github.com:TU-USUARIO/hotboat-marketing-web.git
git branch -M main
git push -u origin main
```

Tras hacer push, revisa en `index.html` que `canonical` y `og:url` coincidan con la URL pública definitiva del sitio.
