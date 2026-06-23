import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { SmartlocksService } from "../../client";

export const Route = createFileRoute("/_layout/locks")({
  component: SmartLockDashboard,
});

function SmartLockDashboard() {
  const queryClient = useQueryClient();

  const [deviceUuid, setDeviceUuid] = useState("001");
  const [bindingKey, setBindingKey] = useState("");

  const {
    data: logs,
    isLoading: isLoadingLogs,
    error: logsError,
  } = useQuery({
    queryKey: ["lockLogs", deviceUuid],
    queryFn: () => SmartlocksService.getLockLogs({ deviceUuid }),
    enabled: !!deviceUuid,
    retry: false,
  });

  const isBound = !!logs && !logsError;

  const bindMutation = useMutation({
    mutationFn: (data: { deviceUuid: string; bindingKeyHex: string }) =>
      SmartlocksService.initiateBind(data),
    onSuccess: (data: any) => {
      alert(data?.message || "綁定請求已發送，請等待設備連線驗證。");
      queryClient.invalidateQueries({ queryKey: ["lockLogs", deviceUuid] });
    },
    onError: (error: any) => {
      alert(error?.body?.detail || "綁定失敗");
    },
  });

  const unbindMutation = useMutation({
    mutationFn: (uuid: string) =>
      SmartlocksService.unbindDevice({ deviceUuid: uuid }),
    onSuccess: (data: any) => {
      alert(data?.message || "雲端已成功強制解除綁定！");
      setBindingKey("");
      queryClient.invalidateQueries({ queryKey: ["lockLogs", deviceUuid] });
    },
    onError: (error: any) => {
      alert(error?.body?.detail || "強制解除綁定失敗");
    },
  });

  const unlockMutation = useMutation({
    mutationFn: (uuid: string) =>
      SmartlocksService.sendUnlockCommand({ deviceUuid: uuid }),
    onSuccess: (data: any) => {
      alert(data?.message || "開鎖指令已成功送出");
      queryClient.invalidateQueries({ queryKey: ["lockLogs", deviceUuid] });
    },
    onError: (error: any) => {
      alert(error?.body?.detail || "開鎖失敗");
    },
  });

  const handleBind = (e: React.SyntheticEvent) => {
    e.preventDefault();
    bindMutation.mutate({
      deviceUuid: deviceUuid,
      bindingKeyHex: bindingKey,
    });
  };

  const handleUnbind = () => {
    const confirmMessage = `確定要【強制解除】設備 [${deviceUuid}] 的綁定嗎？`;

    if (window.confirm(confirmMessage)) {
      unbindMutation.mutate(deviceUuid);
    }
  };

  return (
    <div className="container mx-auto p-6 max-w-4xl space-y-8">
      <h1 className="text-3xl font-bold text-gray-800 border-b pb-4">
        智慧鎖控制中心
      </h1>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* --- 裝置狀態與綁定區塊 --- */}
        <div className="bg-white p-6 rounded-xl shadow-md border border-gray-100 flex flex-col justify-between">
          <div>
            <h2 className="text-xl font-semibold mb-4 text-gray-700">
              裝置狀態與綁定
            </h2>

            {isBound ? (
              <div className="text-center py-6 space-y-3 bg-emerald-50/50 rounded-xl border border-emerald-100 p-4">
                <div className="text-5xl animate-bounce">✅</div>
                <p className="text-emerald-700 font-bold text-lg">
                  此裝置已成功啟用！
                </p>
                <p className="text-gray-500 text-xs font-mono bg-white inline-block px-2 py-1 rounded border">
                  UUID: {deviceUuid}
                </p>

                <div className="pt-3 border-t border-gray-200 mt-2 space-y-2">
                  <button
                    onClick={handleUnbind}
                    disabled={unbindMutation.isPending}
                    className="w-full text-sm bg-amber-50 hover:bg-amber-100 text-amber-700 font-semibold py-2 px-3 rounded-lg border border-amber-200 transition disabled:opacity-50 cursor-pointer"
                  >
                    {unbindMutation.isPending
                      ? "正在強制解除..."
                      : "⚠️ 強制解除綁定"}
                  </button>

                  <div>
                    <button
                      type="button"
                      onClick={() => {
                        const newUuid = prompt(
                          "請輸入要切換檢視的 Device UUID:",
                          deviceUuid,
                        );
                        if (newUuid) setDeviceUuid(newUuid);
                      }}
                      className="text-xs text-blue-600 hover:underline block mx-auto pt-1 cursor-pointer"
                    >
                      切換其他裝置 UUID 檢視
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <form onSubmit={handleBind} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-600 mb-1">
                    Device UUID
                  </label>
                  <input
                    type="text"
                    className="w-full border border-gray-300 rounded-lg p-2 focus:ring-2 focus:ring-blue-500 outline-none"
                    value={deviceUuid}
                    onChange={(e) => setDeviceUuid(e.target.value)}
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-600 mb-1">
                    Binding Key (Hex)
                  </label>
                  <input
                    type="text"
                    className="w-full border border-gray-300 rounded-lg p-2 focus:ring-2 focus:ring-blue-500 outline-none"
                    value={bindingKey}
                    onChange={(e) => setBindingKey(e.target.value)}
                    placeholder="e.g. 15d275a2142140f..."
                    required
                  />
                </div>
                <button
                  type="submit"
                  disabled={bindMutation.isPending}
                  className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-4 rounded-lg transition disabled:bg-blue-300 cursor-pointer"
                >
                  {bindMutation.isPending
                    ? "發送綁定請求中..."
                    : "發起裝置綁定"}
                </button>
              </form>
            )}
          </div>
        </div>

        {/* --- 遠端控制區塊 --- */}
        <div className="bg-white p-6 rounded-xl shadow-md border border-gray-100 flex flex-col justify-center items-center space-y-4">
          <h2 className="text-xl font-semibold text-gray-700">遠端控制</h2>
          <p className="text-gray-500 text-sm text-center max-w-xs">
            透過安全金鑰加密通道，一鍵經由 MQTT 遠端開啟您的智慧門鎖。
          </p>
          <button
            type="button"
            onClick={() => unlockMutation.mutate(deviceUuid)}
            disabled={unlockMutation.isPending || !isBound}
            className={`w-48 h-48 rounded-full text-white text-2xl font-bold shadow-lg transition transform flex items-center justify-center flex-col gap-1 ${
              isBound
                ? "bg-emerald-500 hover:bg-emerald-600 shadow-emerald-500/30 hover:scale-105 active:scale-95 cursor-pointer"
                : "bg-gray-200 text-gray-400 shadow-none cursor-not-allowed"
            }`}
          >
            <span>{unlockMutation.isPending ? "開鎖中..." : "一鍵開鎖"}</span>
            {!isBound && (
              <span className="text-[11px] font-normal text-gray-400">
                (請先完成裝置綁定)
              </span>
            )}
          </button>
        </div>
      </div>

      {/* --- 歷史日誌與安全紀錄區塊 --- */}
      <div className="bg-white p-6 rounded-xl shadow-md border border-gray-100">
        <h2 className="text-xl font-semibold mb-4 text-gray-700">
          門鎖安全日誌
        </h2>

        {isLoadingLogs ? (
          <p className="text-gray-500 text-center py-4">
            連線讀取安全日誌中...
          </p>
        ) : !isBound || !logs || (logs as any).length === 0 ? (
          <p className="text-gray-500 text-center py-8 bg-gray-50 rounded-lg">
            {!isBound
              ? "請先完成裝置綁定以啟用安全日誌系統。"
              : "目前尚無任何活動與開鎖紀錄。"}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm whitespace-nowrap">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="px-4 py-3 font-medium rounded-tl-lg">時間</th>
                  <th className="px-4 py-3 font-medium">認證狀態</th>
                  <th className="px-4 py-3 font-medium">驗證類型</th>
                  <th className="px-4 py-3 font-medium rounded-tr-lg">
                    現場快照
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {(logs as any).map((log: any, index: number) => (
                  <tr key={index} className="hover:bg-gray-50 transition">
                    <td className="px-4 py-3">
                      {new Date(log.timestamp).toLocaleString()}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-1 rounded-full text-xs font-semibold ${
                          log.authenticated
                            ? "bg-green-100 text-green-700"
                            : "bg-red-100 text-red-700"
                        }`}
                      >
                        {log.authenticated ? "驗證成功" : "驗證失敗"}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-gray-600">
                      {log.type}
                    </td>
                    <td className="px-4 py-3">
                      {log.image ? (
                        <img
                          src={`data:image/jpeg;base64,${log.image}`}
                          alt="開鎖快照"
                          className="w-12 h-12 object-cover rounded-md border shadow-sm"
                        />
                      ) : (
                        <span className="text-gray-400 text-xs">
                          無影像紀錄
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
