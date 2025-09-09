# Study App

A Flask web application for study session tracking with Tailwind CSS styling.

## Development Setup

### Prerequisites

- Python 3.x
- Node.js and npm

### Installation

1. Install Python dependencies:

```bash
pip install -r requirements.txt
```

2. Install Node.js dependencies:

```bash
npm install
```

### Development

#### CSS Development

For development with CSS watching (automatically rebuilds when you modify CSS):

```bash
npm run build-css
```

Or use the development script:

```bash
./dev-build.sh
```

#### Production CSS Build

For production (minified CSS):

```bash
npm run build-css-prod
```

#### Running the Flask App

```bash
python app.py
```

## Project Structure

- `app.py` - Main Flask application
- `templates/` - Jinja2 templates
  - `layouts/` - Base layouts
- `static/` - Static assets
  - `css/` - CSS files
    - `input.css` - Tailwind source file
    - `tailwind.css` - Compiled CSS output
  - `images/` - Image assets
- `tailwind.config.js` - Tailwind configuration
- `package.json` - Node.js dependencies and scripts

## Custom CSS Classes

The project includes custom Tailwind components in `static/css/input.css`:

- `.btn-primary` - Primary button styling
- `.btn-secondary` - Secondary button styling
- `.btn-danger` - Danger/delete button styling
- `.form-input` - Form input styling
- `.popup` - Modal popup styling
- `.nav-link` - Navigation link styling
- Timer button classes (`.start-button`, `.stop-button`)

## Notes

- The compiled CSS is committed to the repository for easy deployment
- For development, use `npm run build-css` to watch for changes
- For production deployment, run `npm run build-css-prod` to generate minified CSS
