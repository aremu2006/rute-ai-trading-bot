# Creating Icons for RUTE Extension

Since we can't programmatically generate actual image files, you'll need to create icon images manually.

## Option 1: Use an Online Icon Generator

Visit one of these sites:
- https://www.icoconverter.com/
- https://favicon.io/
- https://realfavicongenerator.net/

Create icons with these specifications:
- Design: A trending upward arrow or chart symbol
- Colors: Blue gradient (#0ea5e9 to #06b6d4)
- Background: Dark (#0f172a)
- Sizes needed: 16x16, 32x32, 48x48, 128x128 pixels
- Format: PNG

## Option 2: Use Design Software

### Figma/Canva:
1. Create a 128x128 canvas
2. Add a trending up arrow icon
3. Use blue gradient colors
4. Export as PNG at 128x128, 48x48, 32x32, and 16x16

### Photoshop/GIMP:
1. Create new image 128x128 pixels
2. Design a simple trading icon (arrow, chart, etc.)
3. Resize and export to different sizes

## Option 3: Use Emoji/Simple Shape

For quick testing, you can:
1. Take a screenshot of the 📈 emoji
2. Resize to 128x128, 48x48, 32x32, 16x16
3. Save as PNG files

## File Placement

Save the icons in:
```
RUTE/public/icons/
├── icon16.png
├── icon32.png
├── icon48.png
└── icon128.png
```

## Temporary Workaround

For testing without icons, the extension will still work - Chrome will just show a default placeholder icon. You can add the icons later.

## Icon Design Tips

- Keep it simple and recognizable
- Use high contrast colors
- Make sure it's visible at 16x16 (smallest size)
- Brand colors: Blue (#0ea5e9), Cyan (#06b6d4)
- Consider adding "RUTE" text on the 128x128 version
