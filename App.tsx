
import React, { useMemo, useState } from "react";
import QRCode from "qrcode";

type VehicleType = "forklift" | "wheelLoader" | "dump";
type CheckStatus = "良好" | "異常あり" | "対象外";

const vehicleLabels: Record<VehicleType, string> = {
  forklift: "フォークリフト",
  wheelLoader: "ホイールローダー",
  dump: "ダンプ",
};

const checkItems: Record<VehicleType, { id: string; label: string; lawNote: string }[]> = {
  forklift: [
    { id: "brake", label: "制動装置・ブレーキの効き", lawNote: "作業開始前点検" },
    { id: "steering", label: "操縦装置・ハンドル操作", lawNote: "作業開始前点検" },
    { id: "hydraulic", label: "荷役装置・油圧装置・油漏れ", lawNote: "作業開始前点検" },
    { id: "fork", label: "フォーク・マスト・チェーンの損傷", lawNote: "安全確認" },
    { id: "tire", label: "タイヤ・ホイール・ナットの緩み", lawNote: "作業開始前点検" },
    { id: "light", label: "前照灯・方向指示器・警報装置", lawNote: "作業開始前点検" },
    { id: "battery", label: "燃料・バッテリー・充電状態", lawNote: "日常確認" },
  ],
  wheelLoader: [
    { id: "brake", label: "ブレーキの効き", lawNote: "作業開始前点検" },
    { id: "clutch", label: "クラッチ・走行操作", lawNote: "作業開始前点検" },
    { id: "bucket", label: "バケット・アーム・ピンの損傷", lawNote: "安全確認" },
    { id: "hydraulic", label: "油圧装置・油漏れ", lawNote: "安全確認" },
    { id: "tire", label: "タイヤ・ホイール・ナットの緩み", lawNote: "安全確認" },
    { id: "light", label: "灯火類・警報ブザー・バックブザー", lawNote: "安全確認" },
    { id: "fluid", label: "燃料・エンジンオイル・冷却水", lawNote: "日常確認" },
  ],
  dump: [
    { id: "brake", label: "ブレーキペダルの踏みしろ・効き", lawNote: "日常点検" },
    { id: "tire", label: "タイヤ空気圧・亀裂・異常摩耗", lawNote: "日常点検" },
    { id: "nut", label: "ホイールナットの緩み", lawNote: "日常点検" },
    { id: "light", label: "灯火類・方向指示器・反射器", lawNote: "日常点検" },
    { id: "fluid", label: "エンジンオイル・冷却水・ブレーキ液", lawNote: "日常点検" },
    { id: "load", label: "荷台・あおり・ダンプ装置・油漏れ", lawNote: "安全確認" },
    { id: "license", label: "車検証・自賠責・運行前確認", lawNote: "運行前確認" },
  ],
};

const emptyStatus = (type: VehicleType): Record<string, CheckStatus> =>
  Object.fromEntries(checkItems[type].map((item) => [item.id, "良好"])) as Record<string, CheckStatus>;

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "13px", borderRadius: 12, border: "1px solid #d1d5db",
  fontSize: 16, boxSizing: "border-box"
};

const cardStyle: React.CSSProperties = {
  background: "#fff", border: "1px solid #e5e7eb", borderRadius: 16,
  padding: 16, marginBottom: 14, boxShadow: "0 1px 4px rgba(0,0,0,0.06)"
};

export default function App() {
  const [vehicleType, setVehicleType] = useState<VehicleType>("forklift");
  const [vehicleName, setVehicleName] = useState("");
  const [inspector, setInspector] = useState("");
  const [meter, setMeter] = useState("");
  const [statuses, setStatuses] = useState<Record<string, CheckStatus>>(emptyStatus("forklift"));
  const [abnormalDetail, setAbnormalDetail] = useState("");
  const [actionDetail, setActionDetail] = useState("");
  const [photoName, setPhotoName] = useState("");
  const [managerName, setManagerName] = useState("");
  const [shareUrl, setShareUrl] = useState("");
  const [qrImage, setQrImage] = useState("");
  const [tab, setTab] = useState<"check" | "history" | "qr">("check");
  const [records, setRecords] = useState<any[]>(() => {
    const saved = localStorage.getItem("heavyVehicleInspectionRecords");
    return saved ? JSON.parse(saved) : [];
  });

  const items = checkItems[vehicleType];
  const hasAbnormal = useMemo(() => Object.values(statuses).some((s) => s === "異常あり"), [statuses]);
  const usable = !hasAbnormal;

  const saveRecords = (next: any[]) => {
    setRecords(next);
    localStorage.setItem("heavyVehicleInspectionRecords", JSON.stringify(next));
  };

  const submit = () => {
    if (!vehicleName || !inspector) return alert("車両名・点検者名を入力してください。");
    if (hasAbnormal && (!abnormalDetail || !actionDetail || !photoName)) {
      return alert("異常ありの場合は、異常内容・対応内容・写真添付が必須です。");
    }
    const record = {
      id: crypto.randomUUID(),
      dateTime: new Date().toLocaleString("ja-JP"),
      vehicleType, vehicleName, inspector, meter,
      items: items.map((item) => ({ itemId: item.id, label: item.label, status: statuses[item.id] })),
      abnormalDetail, actionDetail, photoName, usable,
      managerConfirmed: false, managerName: "",
    };
    saveRecords([record, ...records]);
    setMeter(""); setAbnormalDetail(""); setActionDetail(""); setPhotoName("");
    setStatuses(emptyStatus(vehicleType));
    alert("点検記録を保存しました。");
  };

  const confirmManager = (id: string) => {
    if (!managerName) return alert("管理者名を入力してください。");
    saveRecords(records.map((r) => r.id === id ? { ...r, managerConfirmed: true, managerName } : r));
  };

  const exportCsv = () => {
    const header = ["日時","車種","車両名","点検者","メーター","使用可否","管理者確認","異常内容","対応内容","写真","点検項目"];
    const rows = records.map((r) => [
      r.dateTime, vehicleLabels[r.vehicleType as VehicleType], r.vehicleName, r.inspector, r.meter,
      r.usable ? "使用可" : "使用不可",
      r.managerConfirmed ? `確認済 ${r.managerName}` : "未確認",
      r.abnormalDetail, r.actionDetail, r.photoName,
      r.items.map((i: any) => `${i.label}:${i.status}`).join(" / ")
    ]);
    const csv = [header, ...rows].map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(",")).join("\n");
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "始業前点検記録.csv"; a.click();
    URL.revokeObjectURL(url);
  };

  const makeQr = async () => {
    const url = shareUrl || window.location.href;
    setQrImage(await QRCode.toDataURL(url, { width: 340, margin: 2 }));
  };

  return (
    <div style={{ background: "#f3f4f6", minHeight: "100vh", color: "#111827", paddingBottom: 85 }}>
      <div style={{ maxWidth: 760, margin: "0 auto", padding: 14 }}>
        <h1 style={{ fontSize: 23, marginBottom: 4 }}>重機・車両 始業前点検</h1>
        <p style={{ marginTop: 0, color: "#4b5563" }}>フォークリフト・ホイールローダー・ダンプ対応</p>

        {tab === "check" && <>
          <div style={cardStyle}>
            <h2 style={{ fontSize: 18 }}>基本情報</h2>
            <label>車種</label>
            <select style={inputStyle} value={vehicleType} onChange={(e) => {
              const next = e.target.value as VehicleType; setVehicleType(next); setStatuses(emptyStatus(next));
            }}>
              <option value="forklift">フォークリフト</option>
              <option value="wheelLoader">ホイールローダー</option>
              <option value="dump">ダンプ</option>
            </select>
            <div style={{ height: 10 }} />
            <label>車両番号・車両名</label>
            <input style={inputStyle} value={vehicleName} onChange={(e) => setVehicleName(e.target.value)} placeholder="例：リフト1号 / ダンプ2号" />
            <div style={{ height: 10 }} />
            <label>点検者名</label>
            <input style={inputStyle} value={inspector} onChange={(e) => setInspector(e.target.value)} placeholder="氏名" />
            <div style={{ height: 10 }} />
            <label>メーター・走行距離・アワーメーター</label>
            <input style={inputStyle} value={meter} onChange={(e) => setMeter(e.target.value)} placeholder="例：1234h / 56000km" />
          </div>

          <div style={cardStyle}>
            <h2 style={{ fontSize: 18 }}>点検項目</h2>
            {items.map((item) => (
              <div key={item.id} style={{
                border: "1px solid #e5e7eb", borderRadius: 12, padding: 12, marginBottom: 10,
                background: statuses[item.id] === "異常あり" ? "#fee2e2" : "#fafafa"
              }}>
                <strong>{item.label}</strong>
                <div style={{ fontSize: 12, color: "#6b7280", margin: "4px 0 8px" }}>{item.lawNote}</div>
                <select style={inputStyle} value={statuses[item.id]} onChange={(e) => setStatuses({ ...statuses, [item.id]: e.target.value as CheckStatus })}>
                  <option value="良好">良好</option><option value="異常あり">異常あり</option><option value="対象外">対象外</option>
                </select>
              </div>
            ))}
          </div>

          {hasAbnormal && <div style={{ ...cardStyle, border: "2px solid #ef4444" }}>
            <h2 style={{ fontSize: 18, color: "#b91c1c" }}>異常報告 ※必須</h2>
            <label>異常内容</label>
            <textarea style={{ ...inputStyle, minHeight: 80 }} value={abnormalDetail} onChange={(e) => setAbnormalDetail(e.target.value)} placeholder="どこが、どう悪いか" />
            <div style={{ height: 10 }} />
            <label>対応内容</label>
            <textarea style={{ ...inputStyle, minHeight: 80 }} value={actionDetail} onChange={(e) => setActionDetail(e.target.value)} placeholder="使用停止、修理依頼、管理者報告など" />
            <div style={{ height: 10 }} />
            <label>写真添付</label>
            <input style={inputStyle} type="file" accept="image/*" capture="environment" onChange={(e) => setPhotoName(e.target.files?.[0]?.name || "")} />
            <p style={{ color: "#b91c1c", fontWeight: "bold" }}>異常ありのため、この車両は使用不可で保存されます。</p>
          </div>}

          <div style={cardStyle}>
            <h2 style={{ fontSize: 18 }}>判定</h2>
            <div style={{ padding: 14, borderRadius: 12, background: usable ? "#dcfce7" : "#fee2e2", fontWeight: "bold", fontSize: 20 }}>
              {usable ? "使用可" : "使用不可"}
            </div>
            <button onClick={submit} style={{ width: "100%", padding: 15, marginTop: 14, border: "none", borderRadius: 12, background: "#111827", color: "#fff", fontSize: 17, fontWeight: "bold" }}>
              点検記録を保存
            </button>
          </div>
        </>}

        {tab === "history" && <>
          <div style={cardStyle}>
            <h2 style={{ fontSize: 18 }}>管理・出力</h2>
            <label>管理者名</label>
            <input style={inputStyle} value={managerName} onChange={(e) => setManagerName(e.target.value)} placeholder="管理者確認に使用" />
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button onClick={exportCsv} style={{ ...inputStyle, background: "#fff" }}>CSV出力</button>
              <button onClick={() => window.print()} style={{ ...inputStyle, background: "#fff" }}>PDF印刷</button>
            </div>
          </div>
          <div style={cardStyle}>
            <h2 style={{ fontSize: 18 }}>点検履歴</h2>
            {records.length === 0 && <p>まだ記録がありません。</p>}
            {records.map((r) => (
              <div key={r.id} style={{ border: "1px solid #e5e7eb", borderRadius: 12, padding: 12, marginBottom: 10, background: r.usable ? "#fff" : "#fff1f2" }}>
                <strong>{r.dateTime} / {vehicleLabels[r.vehicleType as VehicleType]} / {r.vehicleName}</strong>
                <p>点検者：{r.inspector}　判定：<b style={{ color: r.usable ? "#15803d" : "#b91c1c" }}>{r.usable ? "使用可" : "使用不可"}</b></p>
                {!r.usable && <>
                  <p>異常内容：{r.abnormalDetail}</p><p>対応内容：{r.actionDetail}</p><p>写真：{r.photoName}</p>
                  {r.managerConfirmed ? <p style={{ color: "#15803d", fontWeight: "bold" }}>管理者確認済：{r.managerName}</p> :
                    <button onClick={() => confirmManager(r.id)} style={{ padding: 10, borderRadius: 10, border: "none", background: "#2563eb", color: "#fff", fontWeight: "bold" }}>管理者確認</button>}
                </>}
              </div>
            ))}
          </div>
        </>}

        {tab === "qr" && <div style={cardStyle}>
          <h2 style={{ fontSize: 18 }}>QRコード共有</h2>
          <p style={{ color: "#4b5563" }}>Vercelで公開されたURLを入れて、現場に貼るQRコードを作れます。</p>
          <label>共有URL</label>
          <input style={inputStyle} value={shareUrl} onChange={(e) => setShareUrl(e.target.value)} placeholder="例：https://xxxxx.vercel.app" />
          <button onClick={makeQr} style={{ width: "100%", padding: 15, marginTop: 12, border: "none", borderRadius: 12, background: "#111827", color: "#fff", fontSize: 17, fontWeight: "bold" }}>
            QRコード作成
          </button>
          {qrImage && <div style={{ textAlign: "center", marginTop: 18 }}>
            <img src={qrImage} alt="QRコード" style={{ width: 280, maxWidth: "100%" }} />
            <p style={{ fontSize: 13, color: "#6b7280" }}>iPhoneはSafariで開いて「ホーム画面に追加」</p>
            <a href={qrImage} download="始業前点検アプリ_QR.png">QR画像を保存</a>
          </div>}
        </div>}
      </div>

      <div style={{ position: "fixed", bottom: 0, left: 0, right: 0, background: "#fff", borderTop: "1px solid #e5e7eb", display: "flex", padding: "8px 6px" }}>
        {(["check", "history", "qr"] as const).map((key) => (
          <button key={key} onClick={() => setTab(key)} style={{ flex: 1, margin: "0 4px", padding: "11px 6px", border: "none", borderRadius: 14, background: tab === key ? "#111827" : "#f3f4f6", color: tab === key ? "#fff" : "#111827", fontWeight: "bold", fontSize: 15 }}>
            {key === "check" ? "点検" : key === "history" ? "履歴" : "QR"}
          </button>
        ))}
      </div>
    </div>
  );
}
