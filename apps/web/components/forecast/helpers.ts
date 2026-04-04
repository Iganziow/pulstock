export const fmt = (v: string | number) => {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? "0" : Math.round(n).toLocaleString("es-CL");
};

export const fmtDec = (v: string | number, d = 1) => {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? "0" : n.toFixed(d);
};

export const fmtMoney = (v: string | number) => {
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? "$0" : "$" + Math.round(n).toLocaleString("es-CL");
};
