// White-card product mockups shown over the dimmed architectural background.
// Static, illustrative only (no live data). Kept text-small and shadowed to
// read as real product surfaces.

export function ContractReviewMockup() {
  return (
    <div className="bg-white rounded-xl shadow-2xl overflow-hidden text-xs font-sans">
      <div className="bg-gray-50 border-b border-gray-200 px-4 py-2.5 flex items-center gap-2">
        <span className="text-gray-500 text-[10px]">Document: Service_Agreement_2024.docx</span>
      </div>
      <div className="grid grid-cols-[1fr_auto] min-h-[320px]">
        <div className="p-4 border-r border-gray-100 text-gray-700 text-[11px] leading-relaxed space-y-2">
          <p className="font-semibold text-gray-800 text-xs">SERVICE AGREEMENT</p>
          <p>This Service Agreement (&quot;Agreement&quot;) is entered into as of the Effective Date set forth below, by and between the parties identified herein:</p>
          <p>(i) Service Provider Corp., a Delaware corporation duly organized…</p>
          <p>(ii) Client Company Inc., the receiving party of services (&quot;Client&quot;).</p>
          <p className="font-medium text-gray-800 text-xs mt-3">1. Scope of Services</p>
          <p>Service Provider agrees to perform the professional consulting services as described in Schedule A attached hereto.</p>
          <p className="font-medium text-gray-800 text-xs mt-3">2. Term and Termination</p>
          <p>2.2 <span className="font-medium">Auto-Renewal.</span> This Agreement shall automatically renew for successive one-year terms…</p>
          <p className="bg-yellow-100 px-0.5 rounded">
            5(c) Liability Cap. Provider&apos;s total liability shall not exceed the fees paid during the twelve (12) months preceding the claim.
          </p>
        </div>
        <div className="w-52 p-3 bg-gray-50 flex flex-col">
          <p className="text-xs font-semibold text-gray-800 mb-2">Contract Analysis</p>
          <p className="text-[10px] text-red-500 font-medium mb-2">Issues Found (6)</p>
          <div className="space-y-2 flex-1 overflow-hidden">
            <div className="bg-white rounded-lg border border-gray-200 p-2">
              <div className="flex items-center gap-1.5 mb-1">
                <span className="w-1.5 h-1.5 rounded-full bg-red-500 flex-shrink-0" />
                <span className="text-[10px] font-medium text-gray-800">Liability cap too restrictive</span>
              </div>
              <p className="text-[10px] text-gray-500 mb-1">§5(c): 12-month fee cap exposes downside risk.</p>
              <div className="flex gap-1">
                <button className="flex-1 text-[9px] py-0.5 rounded border border-gray-300 text-gray-600">Fix</button>
                <button className="flex-1 text-[9px] py-0.5 rounded bg-gray-800 text-white">Approve</button>
              </div>
            </div>
            {[
              { color: 'bg-red-500', text: 'Auto-renewal clause' },
              { color: 'bg-red-500', text: 'Indemnification scope' },
              { color: 'bg-yellow-400', text: 'Termination terms' },
              { color: 'bg-yellow-400', text: 'Confidentiality period' },
              { color: 'bg-yellow-400', text: 'Dispute resolution' },
            ].map((item) => (
              <div key={item.text} className="flex items-center gap-2 py-1 border-b border-gray-100">
                <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${item.color}`} />
                <span className="text-[10px] text-gray-700">{item.text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function DraftingMockup() {
  return (
    <div className="bg-white rounded-xl shadow-2xl overflow-hidden text-xs font-sans">
      <div className="bg-gray-50 border-b border-gray-200 px-4 py-2.5 flex items-center justify-between">
        <span className="text-gray-500 text-[10px]">Drafting Studio · NDA Template</span>
        <span className="text-[9px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-medium">Auto-filled</span>
      </div>
      <div className="p-4 space-y-3 min-h-[320px] text-[11px] text-gray-700 leading-relaxed">
        <p className="font-semibold text-gray-800 text-xs">MUTUAL NON-DISCLOSURE AGREEMENT</p>
        <p>This Mutual Non-Disclosure Agreement (&quot;Agreement&quot;) is entered into as of <span className="bg-blue-100 px-1 rounded text-blue-800 font-medium">August 30, 2026</span>, between:</p>
        <p><span className="bg-blue-100 px-1 rounded text-blue-800 font-medium">Precedent Inc.</span>, a Delaware corporation (&quot;Disclosing Party&quot;), and</p>
        <p><span className="bg-yellow-100 px-1 rounded text-yellow-800 font-medium">[Counterparty Name]</span>, a <span className="bg-yellow-100 px-1 rounded text-yellow-800 font-medium">[State]</span> corporation (&quot;Receiving Party&quot;).</p>
        <p className="font-medium text-gray-800 mt-3">1. Definition of Confidential Information</p>
        <p>For purposes of this Agreement, &quot;Confidential Information&quot; means any data or information that is proprietary to the Disclosing Party…</p>
        <div className="mt-4 bg-emerald-50 border border-emerald-200 rounded-lg p-3">
          <p className="text-[10px] text-emerald-700 font-medium mb-1">✓ 3 clauses auto-applied from playbook</p>
          <p className="text-[10px] text-emerald-600">Governing law · Mutual NDA boilerplate · Standard term</p>
        </div>
      </div>
    </div>
  );
}

export function CitationMockup() {
  return (
    <div className="bg-white rounded-xl shadow-2xl overflow-hidden text-xs font-sans">
      <div className="bg-gray-50 border-b border-gray-200 px-4 py-2.5 flex items-center justify-between">
        <span className="text-gray-500 text-[10px]">Document Intelligence · Extraction Results</span>
        <span className="text-[9px] bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">47 fields</span>
      </div>
      <div className="p-4 min-h-[320px]">
        <div className="space-y-2">
          {[
            { field: 'Parties', value: 'Service Provider Corp. · Client Company Inc.', offset: '§1 · offset 0–82' },
            { field: 'Effective Date', value: 'January 1, 2025', offset: 'Preamble · offset 183–201' },
            { field: 'Term', value: '12 months, auto-renewing', offset: '§2.1–2.2 · offset 512–580' },
            { field: 'Liability Cap', value: '12-month fees paid', offset: '§5(c) · offset 1,482–1,520', flag: 'High Risk' },
            { field: 'Governing Law', value: 'Delaware', offset: '§14 · offset 3,204–3,228' },
            { field: 'Termination Notice', value: '30 days written notice', offset: '§2.2 · offset 602–641' },
            { field: 'Payment Terms', value: 'Net-30 from invoice date', offset: '§4.1 · offset 892–930' },
          ].map((row) => (
            <div key={row.field} className="grid grid-cols-[100px_1fr] gap-3 py-1.5 border-b border-gray-100">
              <span className="text-[10px] text-gray-500 font-medium">{row.field}</span>
              <div>
                <span className="text-[11px] text-gray-800">{row.value}</span>
                {row.flag && (
                  <span className="ml-2 text-[9px] bg-red-100 text-red-700 px-1.5 py-0.5 rounded-full">{row.flag}</span>
                )}
                <p className="text-[9px] text-gray-400 font-mono mt-0.5">{row.offset}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function TabularMockup() {
  const rows = [
    { name: 'Acme MSA 2024', cap: '$2.0M', law: 'Delaware', renew: 'Auto', risk: 'Low' },
    { name: 'Globex SaaS', cap: 'Fees paid', law: 'New York', renew: 'Manual', risk: 'High' },
    { name: 'Initech DPA', cap: '$5.0M', law: 'England', renew: 'Auto', risk: 'Med' },
    { name: 'Umbrella NDA', cap: 'Mutual', law: 'California', renew: 'None', risk: 'Low' },
    { name: 'Stark Vendor', cap: '$1.0M', law: 'Texas', renew: 'Manual', risk: 'Med' },
  ];
  const riskColor: Record<string, string> = {
    Low: 'bg-emerald-100 text-emerald-700',
    Med: 'bg-yellow-100 text-yellow-700',
    High: 'bg-red-100 text-red-700',
  };
  return (
    <div className="bg-white rounded-xl shadow-2xl overflow-hidden text-xs font-sans">
      <div className="bg-gray-50 border-b border-gray-200 px-4 py-2.5 flex items-center justify-between">
        <span className="text-gray-500 text-[10px]">Tabular Review · 248 contracts</span>
        <span className="text-[9px] bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">+ NL column</span>
      </div>
      <div className="p-4 min-h-[320px] overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="text-[9px] uppercase tracking-wide text-gray-400 border-b border-gray-200">
              <th className="py-1.5 font-medium">Contract</th>
              <th className="py-1.5 font-medium">Liability cap</th>
              <th className="py-1.5 font-medium">Gov. law</th>
              <th className="py-1.5 font-medium">Renewal</th>
              <th className="py-1.5 font-medium">Risk</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name} className="border-b border-gray-100 text-[10px] text-gray-700">
                <td className="py-2 font-medium text-gray-800">{r.name}</td>
                <td className="py-2">{r.cap}</td>
                <td className="py-2">{r.law}</td>
                <td className="py-2">{r.renew}</td>
                <td className="py-2">
                  <span className={`px-1.5 py-0.5 rounded-full text-[9px] font-medium ${riskColor[r.risk]}`}>{r.risk}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-[9px] text-gray-400 mt-3">Every cell traces to a character-level citation in its source contract.</p>
      </div>
    </div>
  );
}

export function MonitorMockup() {
  const alerts = [
    { t: 'Renewal window', c: 'Globex SaaS renews in 47 days', tag: 'Recommend renegotiate', tone: 'amber' },
    { t: 'Deadline', c: 'SOC 2 evidence due for Acme MSA', tag: '9 days', tone: 'red' },
    { t: 'Compliance', c: 'Initech DPA subprocessor added', tag: 'Review', tone: 'amber' },
    { t: 'Renewal window', c: 'Stark Vendor auto-renews', tag: 'Recommend close', tone: 'emerald' },
  ];
  const tone: Record<string, string> = {
    red: 'bg-red-500',
    amber: 'bg-yellow-400',
    emerald: 'bg-emerald-500',
  };
  return (
    <div className="bg-white rounded-xl shadow-2xl overflow-hidden text-xs font-sans">
      <div className="bg-gray-50 border-b border-gray-200 px-4 py-2.5 flex items-center justify-between">
        <span className="text-gray-500 text-[10px]">Obligations &amp; Monitoring · Daily pass</span>
        <span className="text-[9px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-medium">4 alerts fired</span>
      </div>
      <div className="p-4 min-h-[320px] space-y-2">
        {alerts.map((a) => (
          <div key={a.c} className="bg-white rounded-lg border border-gray-200 p-2.5">
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-1.5">
                <span className={`w-1.5 h-1.5 rounded-full ${tone[a.tone]}`} />
                <span className="text-[10px] font-medium text-gray-800">{a.t}</span>
              </div>
              <span className="text-[9px] bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded-full">{a.tag}</span>
            </div>
            <p className="text-[10px] text-gray-500">{a.c}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
