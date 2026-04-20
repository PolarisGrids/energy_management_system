import { Construction } from 'lucide-react'

export default function Placeholder({ title }) {
  return (
    <div className="flex items-center justify-center h-full animate-slide-up">
      <div className="glass-card p-12 text-center max-w-md">
        <Construction size={48} className="mx-auto mb-4 text-accent-blue opacity-50" />
        <div className="text-white font-bold text-xl mb-2">{title}</div>
        <div className="text-white/40">This module is being built — Phase {title.includes('HES') || title.includes('MDMS') ? 3 : title.includes('DER') || title.includes('Energy') ? 4 : 5} implementation.</div>
      </div>
    </div>
  )
}
