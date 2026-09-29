import React, { useEffect, useState } from 'react';
import { SimulationResult } from '../types';
import { FileText, Printer } from 'lucide-react';

interface ReportViewProps {
  simulation: SimulationResult | null;
}

export const ReportView: React.FC<ReportViewProps> = ({ simulation }) => {
  const [reportHtml, setReportHtml] = useState<string>('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!simulation?.id) return;
    setLoading(true);
    fetch(`/api/reports/generate/${simulation.id}`)
      .then(res => res.text())
      .then(html => {
        setReportHtml(html);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, [simulation?.id]);

  const handlePrint = () => {
    const printWindow = window.open('', '_blank');
    if (printWindow) {
      printWindow.document.write(reportHtml);
      printWindow.document.close();
      printWindow.focus();
      printWindow.print();
    }
  };

  return (
    <div className="flex-1 bg-slate-950 p-6 flex flex-col overflow-hidden">
      <div className="flex items-center justify-between pb-4 border-b border-slate-800 mb-4 max-w-5xl mx-auto w-full">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <FileText className="w-5 h-5 text-blue-400" />
            <span>Scientific Technical Report</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Automated hydraulic and hydrodynamic inundation assessment report.
          </p>
        </div>

        <button
          onClick={handlePrint}
          disabled={!reportHtml}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs transition shadow-lg shadow-blue-900/30 disabled:opacity-50"
        >
          <Printer className="w-4 h-4" />
          <span>Print / Save as PDF</span>
        </button>
      </div>

      <div className="flex-1 max-w-5xl mx-auto w-full bg-white rounded-xl shadow-2xl overflow-hidden border border-slate-700">
        {loading ? (
          <div className="flex items-center justify-center h-full text-slate-500 text-sm">
            Generating scientific report...
          </div>
        ) : reportHtml ? (
          <iframe
            srcDoc={reportHtml}
            title="Scientific Technical Report"
            className="w-full h-full border-none"
          />
        ) : (
          <div className="flex items-center justify-center h-full text-slate-500 text-sm">
            No simulation results available yet. Run a simulation to generate report.
          </div>
        )}
      </div>
    </div>
  );
};
