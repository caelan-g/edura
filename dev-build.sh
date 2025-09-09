#!/bin/bash
# Development build script
echo "Starting Tailwind CSS development build..."
npm run build-css &
echo "Tailwind CSS is watching for changes..."
echo "Press Ctrl+C to stop"
wait
