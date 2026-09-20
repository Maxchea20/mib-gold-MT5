export async function saveTextFile(filename, text, mime) {
  if (window.showSaveFilePicker) {
    const ext = filename.endsWith(".json") ? ".json" : ".txt";
    const handle = await window.showSaveFilePicker({
      suggestedName: filename,
      types: [{ description: "Backtest report", accept: { [mime]: [ext] } }],
    });
    const w = await handle.createWritable();
    await w.write(text);
    await w.close();
    return "saved";
  }
  try {
    await navigator.clipboard.writeText(text);
    return "copied";
  } catch (_) {}
  const blob = new Blob([text], { type: mime + ";charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { a.remove(); URL.revokeObjectURL(url); }, 1500);
  return "download";
}
