"use client";

import { useState, useCallback } from "react";
import { Upload, FileText, CheckCircle, AlertCircle, Loader2 } from "lucide-react";
import { PageHeader, GlassCard } from "@/components/GlassCard";
import { api, formatINR } from "@/lib/api";

export default function UploadPage() {
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFile = useCallback(async (file: File) => {
    setError(null);
    setResult(null);
    setUploading(true);

    try {
      let res;
      if (file.name.toLowerCase().endsWith(".csv")) {
        res = await api.uploadCSV(file);
      } else if (file.name.toLowerCase().endsWith(".pdf")) {
        res = await api.uploadPDF(file);
      } else {
        throw new Error("Please upload a .csv or .pdf file");
      }
      setResult(res);
    } catch (e: any) {
      setError(e.message || "Upload failed");
    } finally {
      setUploading(false);
    }
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const onFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  return (
    <div>
      <PageHeader
        title="Upload Bank Statement"
        subtitle="Import your bank transactions from CSV or PDF — AI auto-categorizes everything."
      />

      {/* Drop Zone */}
      <GlassCard
        strong
        className={`mb-6 transition-all ${
          dragOver ? "border-mint/50 bg-mint/5" : ""
        }`}
      >
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          className="flex flex-col items-center justify-center py-12 cursor-pointer"
        >
          {uploading ? (
            <>
              <Loader2 size={40} className="text-mint animate-spin mb-4" />
              <p className="text-white font-medium">Processing your bank statement...</p>
              <p className="text-xs text-mist mt-1">AI is categorizing each transaction</p>
            </>
          ) : (
            <>
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-mint/20 to-violet/20 flex items-center justify-center mb-4">
                <Upload size={28} className="text-mint" />
              </div>
              <p className="text-white font-medium mb-1">
                Drag & drop your bank statement here
              </p>
              <p className="text-xs text-mist mb-4">
                Supports CSV and PDF formats • Max 10MB
              </p>
              <label className="h-10 px-6 rounded-xl bg-gradient-to-br from-mint to-violet text-ink text-sm font-medium flex items-center gap-2 cursor-pointer hover:opacity-90 transition-opacity">
                <FileText size={16} />
                Browse Files
                <input
                  type="file"
                  accept=".csv,.pdf"
                  onChange={onFileSelect}
                  className="hidden"
                />
              </label>
            </>
          )}
        </div>
      </GlassCard>

      {/* Error */}
      {error && (
        <GlassCard className="mb-6 !border-rose/30">
          <div className="flex items-center gap-3">
            <AlertCircle size={18} className="text-rose shrink-0" />
            <p className="text-sm text-rose">{error}</p>
          </div>
        </GlassCard>
      )}

      {/* Result */}
      {result && (
        <>
          <GlassCard strong className="mb-6">
            <div className="flex items-center gap-3 mb-4">
              <CheckCircle size={20} className="text-mint" />
              <p className="text-white font-medium">{result.message}</p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-white/[0.03] border border-line rounded-lg p-3">
                <p className="text-xs text-mist mb-1">Parsed</p>
                <p className="ledger text-lg text-white font-medium">{result.total_parsed}</p>
              </div>
              <div className="bg-white/[0.03] border border-line rounded-lg p-3">
                <p className="text-xs text-mist mb-1">Imported</p>
                <p className="ledger text-lg text-mint font-medium">{result.total_inserted}</p>
              </div>
            </div>
          </GlassCard>

          {/* Preview */}
          {result.transactions && result.transactions.length > 0 && (
            <GlassCard>
              <p className="text-sm text-fog mb-3">
                Preview (first {Math.min(result.transactions.length, 20)} transactions)
              </p>
              <div className="overflow-x-auto scrollbar-thin">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-mist border-b border-line">
                      <th className="py-2 pr-4 font-normal">Date</th>
                      <th className="py-2 pr-4 font-normal">Category</th>
                      <th className="py-2 pr-4 font-normal">Merchant</th>
                      <th className="py-2 pr-4 font-normal text-right">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.transactions.map((t: any, i: number) => (
                      <tr key={i} className="border-b border-line/60 last:border-0">
                        <td className="py-2 pr-4 text-mist">
                          {new Date(t.date).toLocaleDateString("en-IN")}
                        </td>
                        <td className="py-2 pr-4 text-white">{t.category}</td>
                        <td className="py-2 pr-4 text-mist">{t.merchant || "—"}</td>
                        <td
                          className={`py-2 pr-4 ledger text-right ${
                            t.amount >= 0 ? "text-mint" : "text-rose"
                          }`}
                        >
                          {t.amount >= 0 ? "+" : ""}
                          {formatINR(t.amount)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </GlassCard>
          )}
        </>
      )}

      {/* Format Guide */}
      <GlassCard className="mt-6">
        <p className="text-sm text-fog mb-3">Supported Formats</p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div>
            <p className="text-white font-medium mb-1">Bank CSV</p>
            <p className="text-xs text-mist">
              Auto-detects columns from SBI, HDFC, ICICI, Axis, and generic formats.
            </p>
          </div>
          <div>
            <p className="text-white font-medium mb-1">UPI Export</p>
            <p className="text-xs text-mist">
              Google Pay, PhonePe, Paytm transaction exports in CSV.
            </p>
          </div>
          <div>
            <p className="text-white font-medium mb-1">PDF Statement</p>
            <p className="text-xs text-mist">
              Bank-generated PDF statements with transaction tables.
            </p>
          </div>
        </div>
      </GlassCard>
    </div>
  );
}
