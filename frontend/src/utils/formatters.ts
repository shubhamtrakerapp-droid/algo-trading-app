export function formatCurrency(amount: number | null | undefined): string {
  if (amount === null || amount === undefined || isNaN(amount)) {
    return '₹0.00';
  }
  const isNegative = amount < 0;
  const abs = Math.abs(amount);
  const formatted = new Intl.NumberFormat('en-IN', {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  }).format(abs);

  return `${isNegative ? '-' : ''}₹${formatted}`;
}

export function formatPoints(points: number | null | undefined): string {
  if (points === null || points === undefined || isNaN(points)) {
    return '0.00 pts';
  }
  const prefix = points > 0 ? '+' : '';
  return `${prefix}${points.toFixed(2)} pts`;
}

export function formatIST(dateStr: string | Date | null | undefined): string {
  if (!dateStr) return '--:--';
  try {
    const d = typeof dateStr === 'string' ? new Date(dateStr) : dateStr;
    if (!d || isNaN(d.getTime())) return '--:--';
    return d.toLocaleTimeString('en-IN', {
      timeZone: 'Asia/Kolkata',
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return '--:--';
  }
}

export function formatISTDate(dateStr: string | Date | null | undefined): string {
  if (!dateStr) return '-';
  try {
    const d = typeof dateStr === 'string' ? new Date(dateStr) : dateStr;
    if (!d || isNaN(d.getTime())) return '-';
    return d.toLocaleDateString('en-IN', {
      timeZone: 'Asia/Kolkata',
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return '-';
  }
}

export function getPnlColor(val: number | null | undefined): string {
  if (val === null || val === undefined || isNaN(val)) return 'text-gray-400';
  if (val > 0) return 'text-emerald-400';
  if (val < 0) return 'text-rose-500';
  return 'text-gray-400';
}

export function getPnlBg(val: number | null | undefined): string {
  if (val === null || val === undefined || isNaN(val)) return 'bg-gray-800/40 border-gray-700/50 text-gray-300';
  if (val > 0) return 'bg-emerald-950/40 border-emerald-800/50 text-emerald-300';
  if (val < 0) return 'bg-rose-950/40 border-rose-800/50 text-rose-300';
  return 'bg-gray-800/40 border-gray-700/50 text-gray-300';
}

export function normalizeDailyAnalytics(day: any): {
  date: string;
  trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  pnl: number;
  grossProfit: number;
  grossLoss: number;
  charges: number;
} {
  if (!day || typeof day !== 'object') {
    return {
      date: 'Unknown',
      trades: 0,
      wins: 0,
      losses: 0,
      win_rate: 0,
      pnl: 0,
      grossProfit: 0,
      grossLoss: 0,
      charges: 0,
    };
  }

  const rawTrades = Number(day?.trades ?? 0);
  const rawWins = Number(day?.wins ?? 0);
  const rawLosses = Number(day?.losses ?? (rawTrades >= rawWins ? rawTrades - rawWins : 0));
  const rawWinRate = Number(day?.win_rate ?? (rawTrades > 0 ? (rawWins / rawTrades) * 100 : 0));
  const rawPnl = Number(day?.pnl ?? day?.net_pnl ?? 0);
  const rawGrossProfit = Number(day?.grossProfit ?? day?.gross_profit ?? 0);
  const rawGrossLoss = Number(day?.grossLoss ?? day?.gross_loss ?? 0);
  const rawCharges = Number(day?.charges ?? day?.total_charges ?? 0);

  return {
    date: String(day?.date || 'Unknown'),
    trades: isNaN(rawTrades) ? 0 : rawTrades,
    wins: isNaN(rawWins) ? 0 : rawWins,
    losses: isNaN(rawLosses) ? 0 : rawLosses,
    win_rate: isNaN(rawWinRate) ? 0 : Math.round(rawWinRate * 10) / 10,
    pnl: isNaN(rawPnl) ? 0 : Math.round(rawPnl * 100) / 100,
    grossProfit: isNaN(rawGrossProfit) ? 0 : Math.round(rawGrossProfit * 100) / 100,
    grossLoss: isNaN(rawGrossLoss) ? 0 : Math.round(rawGrossLoss * 100) / 100,
    charges: isNaN(rawCharges) ? 0 : Math.round(rawCharges * 100) / 100,
  };
}

export function formatCharges(charges: any): string {
  return Number(charges ?? 0).toFixed(2);
}

export function formatDailyMetric(val: any): string {
  return Number(val ?? 0).toFixed(2);
}
