<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Коллаж образа 2500×2500</title>
  <style>
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      background: #111;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    }

    /* Полотно 2500×2500 */
    .canvas {
      position: relative;
      width: 2500px;
      height: 2500px;
      background: #ffffff;
    }

    /* ==================== top_main (джемпер) ==================== */
    .top_main {
      position: absolute;
      left: 840px;
      top: 215px;
      width: 800px;
      text-align: center;
    }
    .top_main-title {
      font-size: 32px;
      font-weight: 500;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      margin-bottom: 6px;
    }
    .top_main-brand {
      font-size: 28px;
      font-weight: 600;
      letter-spacing: 0.28em;
      text-transform: uppercase;
      margin-bottom: 24px;
    }
    .top_main-image {
      display: block;
      width: 800px;   /* фикс по X */
      height: auto;   /* пропорции */
    }

    /* ==================== accessory_upper (шарф) ==================== */
    .accessory_upper {
      position: absolute;
      left: 440px;
      top: 110px;
      width: 400px;
      text-align: left;
    }
    .accessory_upper-title {
      font-size: 24px;
      font-weight: 500;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      margin-bottom: 4px;
    }
    .accessory_upper-brand {
      font-size: 20px;
      font-weight: 600;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      margin-bottom: 12px;
    }
    .accessory_upper-image {
      display: block;
      width: 400px;   /* фикс по X */
      height: auto;
    }

    /* ==================== top_second (куртка) ==================== */
    /* картинка */
    .top_second-image {
      position: absolute;
      left: 220px;
      top: 420px;
      width: 800px;
      height: 1500px;
      text-align: center;
    }
    .top_second-image-img {
      display: block;
      width: 800px;   /* фикс по X */
      height: auto;
      max-height: 1500px;
    }
    /* текст */
    .top_second-text {
      position: absolute;
      left: 20px;
      top: 450px;
      width: 400px;
      text-align: left;
    }
    .top_second-title {
      font-size: 24px;
      font-weight: 500;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      line-height: 1.3;
      margin-bottom: 6px;
      word-wrap: break-word;
    }
    .top_second-brand {
      font-size: 20px;
      font-weight: 600;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      line-height: 1.3;
      word-wrap: break-word;
    }

    /* ==================== bottom (джинсы) ==================== */
    .bottom-image {
      position: absolute;
      left: 1520px;
      top: 960px;
      width: 500px;
      height: 1500px;
      text-align: center;
    }
    .bottom-image-img {
      display: block;
      width: 500px;   /* фикс по X */
      height: auto;
    }
    .bottom-text {
      position: absolute;
      left: 2050px;
      top: 960px;
      width: 400px;
      text-align: left;
    }
    .bottom-title {
      font-size: 24px;
      font-weight: 500;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      line-height: 1.3;
      margin-bottom: 6px;
      word-wrap: break-word;
    }
    .bottom-brand {
      font-size: 20px;
      font-weight: 600;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      line-height: 1.3;
      word-wrap: break-word;
    }

    /* ==================== shoes (кроссовки) ==================== */
    .shoes-row {
      position: absolute;
      left: 500px;          /* чтобы картинка начиналась в x ≈ 1040 */
      top: 2050px;
      width: 1080px;        /* 500 (текст) + 40 (gap) + 540 (картинка) */
      height: 340px;
      display: flex;
      align-items: center;
      column-gap: 40px;
    }
    .shoes-text {
      width: 500px;
      text-align: left;
    }
    .shoes-title {
      font-size: 22px;
      font-weight: 500;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      line-height: 1.4;
      margin-bottom: 6px;
      word-wrap: break-word;
    }
    .shoes-brand {
      font-size: 20px;
      font-weight: 600;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      line-height: 1.3;
      word-wrap: break-word;
    }
    .shoes-image {
      display: block;
      width: 540px;  /* фикс по X */
      height: auto;
      max-height: 340px;
    }

    /* ==================== accessory_lower (рюкзак/сумка) ==================== */
    .accessory_lower {
      position: absolute;
      left: 690px;
      top: 1480px;
      width: 580px;
      height: 500px;
      text-align: left;
    }
    .accessory_lower-title {
      font-size: 22px;
      font-weight: 500;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      line-height: 1.4;
      margin-bottom: 6px;
      word-wrap: break-word;
    }
    .accessory_lower-brand {
      font-size: 20px;
      font-weight: 600;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      line-height: 1.3;
      margin-bottom: 12px;
      word-wrap: break-word;
    }
    .accessory_lower-image {
      display: block;
      width: 580px;  /* фикс по X */
      height: auto;
    }

    @media print {
      body {
        background: #fff;
      }
    }
  </style>
</head>
<body>
  <div class="canvas">

    <!-- top_main (кофта / джемпер) -->
    <div class="top_main">
      <div class="top_main-title">Джемпер из вискозы</div>
      <div class="top_main-brand">VETEMENTS</div>
      <img
        class="top_main-image"
        src="https://cdn.vipavenue.ru/products/1455001_1460000/1458638/compress/0_1739185197.webp"
        alt="Джемпер из вискозы VETEMENTS"
      >
    </div>

    <!-- accessory_upper (шарф) -->
    <div class="accessory_upper">
      <div class="accessory_upper-title">Шарф кашемировый</div>
      <div class="accessory_upper-brand">CESARE GATTI</div>
      <img
        class="accessory_upper-image"
        src="https://cdn.vipavenue.ru/products/1380001_1385000/1383436/compress/0_1757452370.webp"
        alt="Шарф кашемировый CESARE GATTI"
      >
    </div>

    <!-- top_second (куртка) -->
    <div class="top_second-image">
      <img
        class="top_second-image-img"
        src="https://cdn.vipavenue.ru/products/1510001_1515000/1512436/compress/0_1758715423.webp"
        alt="Куртка хлопковая BOSS"
      >
    </div>
    <div class="top_second-text">
      <div class="top_second-title">Куртка хлопковая</div>
      <div class="top_second-brand">BOSS</div>
    </div>

    <!-- bottom (джинсы) -->
    <div class="bottom-image">
      <img
        class="bottom-image-img"
        src="https://cdn.vipavenue.ru/products/1490001_1495000/1491776/compress/0_1750968810.webp"
        alt="Джинсы CLOSED"
      >
    </div>
    <div class="bottom-text">
      <div class="bottom-title">Джинсы</div>
      <div class="bottom-brand">CLOSED</div>
    </div>

    <!-- shoes (кроссовки) -->
    <div class="shoes-row">
      <div class="shoes-text">
        <div class="shoes-title">Кроссовки комбинированные Mased</div>
        <div class="shoes-brand">PREMIATA</div>
      </div>
      <img
        class="shoes-image"
        src="https://cdn.vipavenue.ru/products/1480001_1485000/1481563/compress/1_1745783886.webp"
        alt="Кроссовки комбинированные Mased PREMIATA"
      >
    </div>

    <!-- accessory_lower (рюкзак / сумка) -->
    <div class="accessory_lower">
      <div class="accessory_lower-title">Рюкзак с логотипом</div>
      <div class="accessory_lower-brand">BRUNELLO CUCINELLI</div>
      <img
        class="accessory_lower-image"
        src="https://cdn.vipavenue.ru/products/1465001_1470000/1465874/compress/0_1741462111.webp"
        alt="Рюкзак с логотипом BRUNELLO CUCINELLI"
      >
    </div>

  </div>
</body>
</html>
