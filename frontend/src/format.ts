const DAY = 24 * 60 * 60 * 1000

/** «сегодня», «завтра», «через 6 дней» — когда слово снова появится в повторении. */
export function formatNextReview(iso: string, now = new Date()): string {
  const days = Math.ceil((new Date(iso).getTime() - now.getTime()) / DAY)
  if (days <= 0) return 'сегодня'
  return new Intl.RelativeTimeFormat('ru', { numeric: 'auto' }).format(days, 'day')
}

export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few
  return many
}
