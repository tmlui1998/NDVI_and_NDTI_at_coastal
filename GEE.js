/**** 
Gulf of Finland remote sensing project
Exports monthly NDVI and NDTI rasters
Run one year at a time for stability
****/

// =========================================================
// 1. ROI
// =========================================================
var roi = ee.Geometry.Rectangle([23.5, 59.4 , 30.28, 60.7], null, false);
Map.centerObject(roi, 8);

// =========================================================
// 2. SETTINGS
// =========================================================
var YEAR = 2016;          // Change manually: 2019, 2020, ..., 2024
var EXPORT_SCALE = 95;    // 30 m is lighter than 10 m
var CRS = 'EPSG:3035';
var MONTHS = [5, 6, 7, 8, 9];

// =========================================================
// 3. CLOUD MASK
// =========================================================
function maskS2(img) {
  var qa = img.select('QA60');
  var cloudBitMask = 1 << 10;
  var cirrusBitMask = 1 << 11;

  var qaMask = qa.bitwiseAnd(cloudBitMask).eq(0)
    .and(qa.bitwiseAnd(cirrusBitMask).eq(0));

  var scl = img.select('SCL');
  var sclMask = scl.neq(1)   // saturated/defective
    .and(scl.neq(3))         // cloud shadow
    .and(scl.neq(8))         // cloud medium probability
    .and(scl.neq(9))         // cloud high probability
    .and(scl.neq(10))        // thin cirrus
    .and(scl.neq(11));       // snow/ice

  return img.updateMask(qaMask)
            .updateMask(sclMask)
            .copyProperties(img, img.propertyNames());
}

// =========================================================
// OCEAN / WATER MASK
// =========================================================

// Global Surface Water dataset
var gsw = ee.Image('JRC/GSW1_4/GlobalSurfaceWater');

// Permanent water threshold
var waterMask = gsw.select('seasonality').gte(10).clip(roi);

// Land mask = inverse of water
var landMask = waterMask.not().clip(roi);

// Preview masks
Map.addLayer(waterMask.selfMask(), {palette: ['blue']}, 'Water mask', false);
Map.addLayer(landMask.selfMask(), {palette: ['green']}, 'Land mask', false);

// =========================================================
// 4. ADD INDICES
// =========================================================
function addIndices(img) {
  var ndvi = img.normalizedDifference(['B8', 'B4']).rename('NDVI');
  var ndti = img.normalizedDifference(['B4', 'B3']).rename('NDTI');
  return img.addBands([ndvi, ndti]);
}

// =========================================================
// 5. LOAD SENTINEL-2 FOR ONE YEAR
// =========================================================
var startDate = ee.Date.fromYMD(YEAR, 5, 1);
var endDate = ee.Date.fromYMD(YEAR, 9, 30);

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(roi)
  .filterDate(startDate, endDate)
  .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', 50))
  .map(maskS2)
  .map(addIndices);

print('Image count for ' + YEAR, s2.size());

// =========================================================
// 6. OPTIONAL QUICK PREVIEW
// Keep only one preview layer to avoid freezing
// =========================================================
var julyStart = ee.Date.fromYMD(YEAR, 7, 1);
var julyEnd = julyStart.advance(1, 'month');

var julyNdvi = s2.filterDate(julyStart, julyEnd)
  .select('NDVI')
  .median()
  .clip(roi);

Map.addLayer(
  julyNdvi,
  {min: 0, max: 0.8, palette: ['white', 'yellow', 'green']},
  'July NDVI preview',
  false
);

// =========================================================
// 7. EXPORT MONTH BY MONTH
// =========================================================
MONTHS.forEach(function(month) {

  var monthStart = ee.Date.fromYMD(YEAR, month, 1);
  var monthEnd = monthStart.advance(1, 'month');
  var monthStr = (month < 10 ? '0' + month : '' + month);
  var dateStr = YEAR + '-' + monthStr;

  var monthlyCol = s2.filterDate(monthStart, monthEnd);

  var monthlyNdvi = monthlyCol.select('NDVI')
    .median()
    .clip(roi);

  var monthlyNdti = monthlyCol.select('NDTI')
    .median()
    .clip(roi);

  Export.image.toDrive({
    image: monthlyNdvi,
    description: 'GOF_NDVI_' + dateStr,
    folder: 'GOF_RemoteSensing_Monthly',
    fileNamePrefix: 'GOF_NDVI_' + dateStr,
    region: roi,
    scale: EXPORT_SCALE,
    crs: CRS,
    maxPixels: 1e13
  });

  Export.image.toDrive({
    image: monthlyNdti,
    description: 'GOF_NDTI_' + dateStr,
    folder: 'GOF_RemoteSensing_Monthly',
    fileNamePrefix: 'GOF_NDTI_' + dateStr,
    region: roi,
    scale: EXPORT_SCALE,
    crs: CRS,
    maxPixels: 1e13
  });

});

// =========================================================
// PREVIEW ONE MONTH (for visual check)
// =========================================================

var previewStart = ee.Date.fromYMD(YEAR, 7, 1);
var previewEnd = previewStart.advance(1, 'month');

var previewCollection = s2.filterDate(previewStart, previewEnd);

// NDVI preview
var previewNDVI = previewCollection
  .select('NDVI')
  .median()
  .updateMask(landMask)
  .clip(roi);
  
// NDTI preview
var previewNDTI = previewCollection
  .select('NDTI')
  .median()
  .updateMask(waterMask)
  .clip(roi);

// Add to map
Map.addLayer(
  previewNDVI,
  {min: 0, max: 0.8, palette: ['white','yellow','green']},
  'Preview NDVI July',
  true
);

Map.addLayer(
  previewNDTI,
  {min: -0.2, max: 0.4, palette: ['blue','white','brown']},
  'Preview NDTI July',
  false
);