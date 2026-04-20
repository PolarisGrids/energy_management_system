import { useState, useEffect } from 'react';
import ReactECharts from 'echarts-for-react';
import {
  ShieldCheck, AlertTriangle, CheckCircle, XCircle,
  FileText, Activity, BarChart3, Clock, Minus
} from 'lucide-react';
import { reconcilerAPI } from '../services/api';

const STATUS_COLORS = {
  compliant: '#02C9A8',
  partial: '#F5A623',
  non_compliant: '#E94B4B',
  not_applicable: '#6B7280',
  complete: '#02C9A8',
  not_started: '#E94B4B',
};

function MetricCard({ icon: Icon, label, value, sub, color = '#02C9A8' }) {
  return (
    <div className="rounded-xl p-5" style={{ background: 'linear-gradient(135deg, #0A1A4A 0%, #0D1F5C 100%)', border: '1px solid rgba(255,255,255,0.06)' }}>
      <div className="flex items-center gap-3 mb-2">
        <Icon size={20} style={{ color }} />
        <span className="text-sm text-gray-400">{label}</span>
      </div>
      <div className="text-2xl font-bold text-white">{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </div>
  );
}

function ComplianceMatrix({ matrix }) {
  if (!matrix || matrix.length === 0) return <p className="text-gray-500">No compliance data. Run <code>reconciler audit</code>.</p>;

  // Filter to standards with actual findings (not just zero-row entries)
  const relevant = matrix.filter(m => m.compliant + m.partial + m.non_compliant > 0 || m.not_applicable > 0);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-gray-400 border-b border-gray-700">
            <th className="pb-3 pr-4">Standard</th>
            <th className="pb-3 px-2 text-center">Clauses</th>
            <th className="pb-3 px-2 text-center">&#10003;</th>
            <th className="pb-3 px-2 text-center">~</th>
            <th className="pb-3 px-2 text-center">&#10007;</th>
            <th className="pb-3 px-2 text-center">N/A</th>
            <th className="pb-3 pl-4 text-right">Compliance</th>
          </tr>
        </thead>
        <tbody>
          {relevant.map((row, idx) => (
            <tr key={idx} className="border-b border-gray-800 hover:bg-white/5">
              <td className="py-3 pr-4 text-gray-200 font-medium text-xs">{row.standard}</td>
              <td className="py-3 px-2 text-center text-gray-400">{row.total}</td>
              <td className="py-3 px-2 text-center" style={{ color: STATUS_COLORS.compliant }}>{row.compliant}</td>
              <td className="py-3 px-2 text-center" style={{ color: STATUS_COLORS.partial }}>{row.partial}</td>
              <td className="py-3 px-2 text-center" style={{ color: STATUS_COLORS.non_compliant }}>{row.non_compliant}</td>
              <td className="py-3 px-2 text-center text-gray-500">{row.not_applicable}</td>
              <td className="py-3 pl-4 text-right font-bold" style={{ color: row.compliance_pct >= 80 ? '#02C9A8' : row.compliance_pct >= 50 ? '#F5A623' : '#E94B4B' }}>
                {row.compliance_pct?.toFixed(1)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FeatureStatusChart({ items }) {
  if (!items || items.length === 0) return null;

  const option = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item', formatter: '{b}: {c} pts ({d}%)' },
    legend: { show: false },
    series: [{
      type: 'pie',
      radius: ['55%', '80%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 6, borderColor: '#0A0F1E', borderWidth: 3 },
      label: { show: true, position: 'center', formatter: () => '', fontSize: 0 },
      data: [
        { value: items.filter(i => i.status === 'complete').reduce((s, i) => s + (i.demo_item_score || 0), 0), name: 'Complete', itemStyle: { color: '#02C9A8' } },
        { value: items.filter(i => i.status === 'partial').reduce((s, i) => s + (i.demo_item_score || 0), 0), name: 'Partial', itemStyle: { color: '#F5A623' } },
        { value: items.filter(i => i.status === 'not_started').reduce((s, i) => s + (i.demo_item_score || 0), 0), name: 'Not Started', itemStyle: { color: '#E94B4B' } },
      ].filter(d => d.value > 0),
    }],
  };

  return <ReactECharts option={option} style={{ height: 200 }} />;
}

function FeatureList({ items }) {
  if (!items || items.length === 0) return null;

  return (
    <div className="space-y-1 max-h-96 overflow-y-auto pr-2">
      {items.map((item, idx) => {
        const statusIcon = item.status === 'complete' ? <CheckCircle size={14} style={{ color: '#02C9A8' }} />
          : item.status === 'partial' ? <AlertTriangle size={14} style={{ color: '#F5A623' }} />
          : <XCircle size={14} style={{ color: '#E94B4B' }} />;
        return (
          <div key={idx} className="flex items-center gap-2 py-2 px-3 rounded-lg hover:bg-white/5 text-sm">
            {statusIcon}
            <span className="text-gray-200 flex-1">{item.demo_item_name}</span>
            <span className="text-gray-500 text-xs">{item.demo_item_score} pts</span>
            <span className="text-xs px-2 py-0.5 rounded-full" style={{
              background: item.status === 'complete' ? 'rgba(2,201,168,0.15)' : item.status === 'partial' ? 'rgba(245,166,35,0.15)' : 'rgba(233,75,75,0.15)',
              color: STATUS_COLORS[item.status] || '#6B7280',
            }}>
              {item.signals_found || 0}/4
            </span>
          </div>
        );
      })}
    </div>
  );
}

export default function Reconciler() {
  const [summary, setSummary] = useState(null);
  const [matrix, setMatrix] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const [summaryRes, matrixRes] = await Promise.all([
          reconcilerAPI.getSummary(),
          reconcilerAPI.getComplianceMatrix(),
        ]);
        setSummary(summaryRes.data);
        setMatrix(matrixRes.data.matrix || []);
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to load reconciler data. Ensure reconciler has been run.');
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#02C9A8]" />
    </div>
  );

  if (error) return (
    <div className="rounded-xl p-8 text-center" style={{ background: 'rgba(233,75,75,0.1)', border: '1px solid rgba(233,75,75,0.2)' }}>
      <AlertTriangle size={32} className="mx-auto mb-3 text-red-400" />
      <p className="text-gray-300">{error}</p>
      <p className="text-sm text-gray-500 mt-2">Run <code className="text-[#02C9A8]">reconciler setup && reconciler audit && reconciler features</code> first.</p>
    </div>
  );

  const featureItems = summary?.feature_items || [];
  const featureReport = summary?.feature_report;
  const completeCount = featureReport?.complete_count || 0;
  const totalItems = featureReport?.demo_item_count || 27;
  const projectedScore = featureReport?.total_score_available || 0;
  const projectedPct = ((projectedScore / 133) * 100).toFixed(1);

  const totalCompliant = matrix.reduce((s, m) => s + (m.compliant || 0), 0);
  const totalNonCompliant = matrix.reduce((s, m) => s + (m.non_compliant || 0), 0);
  const totalPartial = matrix.reduce((s, m) => s + (m.partial || 0), 0);
  const totalAssessed = totalCompliant + totalNonCompliant + totalPartial;
  const overallPct = totalAssessed > 0 ? ((totalCompliant / totalAssessed) * 100).toFixed(1) : '—';

  const tabs = [
    { id: 'overview', label: 'Overview', icon: BarChart3 },
    { id: 'compliance', label: 'Compliance', icon: ShieldCheck },
    { id: 'features', label: 'Features', icon: CheckCircle },
  ];

  return (
    <div className="space-y-6">
      {/* Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard icon={ShieldCheck} label="IEC Compliance" value={`${overallPct}%`} sub={`${totalCompliant} compliant / ${totalAssessed} assessed`} color={totalNonCompliant > 0 ? '#E94B4B' : '#02C9A8'} />
        <MetricCard icon={CheckCircle} label="Demo Features" value={`${completeCount}/${totalItems}`} sub={`${projectedScore}/133 pts (${projectedPct}%)`} color={parseFloat(projectedPct) >= 85 ? '#02C9A8' : '#F5A623'} />
        <MetricCard icon={AlertTriangle} label="Non-Compliant" value={totalNonCompliant} sub={`${totalPartial} partial findings`} color={totalNonCompliant > 0 ? '#E94B4B' : '#02C9A8'} />
        <MetricCard icon={FileText} label="Standards Indexed" value={matrix.length} sub="IEC / STS documents" color="#3C63FF" />
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-1 p-1 rounded-lg" style={{ background: 'rgba(255,255,255,0.05)' }}>
        {tabs.map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm transition-all ${activeTab === tab.id ? 'bg-[#3C63FF] text-white' : 'text-gray-400 hover:text-white hover:bg-white/5'}`}>
            <tab.icon size={16} /> {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="rounded-xl p-6" style={{ background: 'linear-gradient(135deg, #0A1A4A 0%, #0D1F5C 100%)', border: '1px solid rgba(255,255,255,0.06)' }}>
            <h3 className="text-white font-semibold mb-4 flex items-center gap-2"><ShieldCheck size={18} style={{ color: '#3C63FF' }} /> Compliance Matrix</h3>
            <ComplianceMatrix matrix={matrix} />
          </div>
          <div className="rounded-xl p-6" style={{ background: 'linear-gradient(135deg, #0A1A4A 0%, #0D1F5C 100%)', border: '1px solid rgba(255,255,255,0.06)' }}>
            <h3 className="text-white font-semibold mb-4 flex items-center gap-2"><CheckCircle size={18} style={{ color: '#02C9A8' }} /> Demo Readiness</h3>
            <FeatureStatusChart items={featureItems} />
            <div className="text-center mt-2">
              <span className="text-2xl font-bold" style={{ color: parseFloat(projectedPct) >= 85 ? '#02C9A8' : '#F5A623' }}>{projectedPct}%</span>
              <span className="text-gray-500 text-sm ml-2">of 133 points</span>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'compliance' && (
        <div className="rounded-xl p-6" style={{ background: 'linear-gradient(135deg, #0A1A4A 0%, #0D1F5C 100%)', border: '1px solid rgba(255,255,255,0.06)' }}>
          <h3 className="text-white font-semibold mb-4">Full Compliance Matrix</h3>
          <ComplianceMatrix matrix={matrix} />
        </div>
      )}

      {activeTab === 'features' && (
        <div className="rounded-xl p-6" style={{ background: 'linear-gradient(135deg, #0A1A4A 0%, #0D1F5C 100%)', border: '1px solid rgba(255,255,255,0.06)' }}>
          <h3 className="text-white font-semibold mb-4">27 SMOC Demo Items — Feature Completion</h3>
          <FeatureList items={featureItems} />
        </div>
      )}
    </div>
  );
}
