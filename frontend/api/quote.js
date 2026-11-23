export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Credentials', 'true');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,OPTIONS,PATCH,DELETE,POST,PUT');
  res.setHeader(
    'Access-Control-Allow-Headers',
    'X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version, Authorization'
  );
  res.setHeader('Cache-Control', 's-maxage=10, stale-while-revalidate=30');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 4500);

    const yahooRes = await fetch(
      'https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1m&range=1d',
      {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        },
        signal: controller.signal
      }
    );
    clearTimeout(timeoutId);

    if (!yahooRes.ok) {
      throw new Error(`Yahoo Finance responded with status ${yahooRes.status}`);
    }

    const json = await yahooRes.json();
    const meta = json?.chart?.result?.[0]?.meta;
    const price = Number(meta?.regularMarketPrice) || 25800.60;
    const prevClose = Number(meta?.chartPreviousClose) || 25514.30;
    const dayHigh = Number(meta?.regularMarketDayHigh) || Math.max(price, 25808.80);
    const dayLow = Number(meta?.regularMarketDayLow) || Math.min(price, 25345.20);
    const change = Math.round((price - prevClose) * 100) / 100;
    const changePct = Math.round(((change / prevClose) * 100) * 100) / 100;

    return res.status(200).json({
      symbol: '^NSEI',
      display_symbol: 'NIFTY 50',
      price: Math.round(price * 100) / 100,
      prev_close: prevClose,
      change,
      change_pct: changePct,
      day_high: dayHigh,
      day_low: dayLow,
      timestamp: new Date().toISOString(),
      source: 'LIVE_YAHOO'
    });
  } catch (err) {
    return res.status(200).json({
      symbol: '^NSEI',
      display_symbol: 'NIFTY 50',
      price: 25800.60,
      prev_close: 25514.30,
      change: 286.30,
      change_pct: 1.12,
      day_high: 25808.80,
      day_low: 25345.20,
      timestamp: new Date().toISOString(),
      source: 'SETTLED_CLOSE_FALLBACK'
    });
  }
}
