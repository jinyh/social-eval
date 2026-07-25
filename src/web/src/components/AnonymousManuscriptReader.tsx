import { Expand, FileText, X } from "lucide-react";
import { useState } from "react";

import type {
  AnonymousManuscript,
  AnonymousManuscriptBlock,
} from "@/lib/types";
import { cn } from "@/lib/utils";

import { Button } from "./ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "./ui/card";

type AnonymousManuscriptReaderProps = {
  manuscript: AnonymousManuscript | null;
  loading?: boolean;
  error?: string;
  showRisks?: boolean;
};

export function AnonymousManuscriptReader({
  manuscript,
  loading = false,
  error,
  showRisks = false,
}: AnonymousManuscriptReaderProps) {
  const [fullscreen, setFullscreen] = useState(false);

  if (loading) {
    return <ReaderState text="正在加载匿名稿……" />;
  }
  if (error) {
    return <ReaderState text={error} tone="error" />;
  }
  if (!manuscript) {
    return <ReaderState text="匿名稿尚未生成。" />;
  }

  const content = (
    <ManuscriptContent manuscript={manuscript} showRisks={showRisks} />
  );
  return (
    <>
      <Card className="overflow-hidden">
        <CardHeader className="border-b border-slate-200 bg-white">
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-blue-700" />
                匿名稿
              </CardTitle>
              <CardDescription>
                稿件编号 {manuscript.manuscript_id} · 第{" "}
                {manuscript.document_version} 版
              </CardDescription>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setFullscreen(true)}
            >
              <Expand className="h-4 w-4" />
              全屏阅读
            </Button>
          </div>
        </CardHeader>
        <CardContent className="max-h-[72vh] overflow-y-auto bg-slate-50 p-4 sm:p-6">
          {content}
        </CardContent>
      </Card>
      {fullscreen ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="匿名稿全屏阅读"
          className="fixed inset-0 z-50 flex flex-col bg-slate-100"
        >
          <div className="flex items-center justify-between border-b border-slate-200 bg-white px-5 py-3">
            <div>
              <p className="font-semibold text-slate-950">匿名稿全屏阅读</p>
              <p className="text-xs text-slate-500">
                稿件编号 {manuscript.manuscript_id}
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={() => setFullscreen(false)}
            >
              <X className="h-4 w-4" />
              退出全屏
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto p-4 sm:p-8">
            <div className="mx-auto max-w-4xl">{content}</div>
          </div>
        </div>
      ) : null}
    </>
  );
}

function ManuscriptContent({
  manuscript,
  showRisks,
}: {
  manuscript: AnonymousManuscript;
  showRisks: boolean;
}) {
  return (
    <article className="mx-auto max-w-4xl rounded-xl border border-slate-200 bg-white px-5 py-7 shadow-sm sm:px-10">
      <p className="mb-6 rounded-lg bg-blue-50 px-3 py-2 text-xs leading-5 text-blue-800">
        {manuscript.notice}
      </p>
      {showRisks && manuscript.risk_flags.length > 0 ? (
        <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
          <p className="text-sm font-medium text-amber-900">编辑匿名核验提示</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-800">
            {manuscript.risk_flags.map((flag) => (
              <li key={flag}>{flag}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="space-y-5">
        {manuscript.blocks.map((block, index) => (
          <ManuscriptBlockView
            key={`${block.type}-${block.page ?? block.number ?? index}-${index}`}
            block={block}
          />
        ))}
      </div>
    </article>
  );
}

function ManuscriptBlockView({
  block,
}: {
  block: AnonymousManuscriptBlock;
}) {
  if (block.type === "page_break") {
    return (
      <div className="flex items-center gap-3 py-2 text-xs text-slate-400">
        <span className="h-px flex-1 bg-slate-200" />
        第 {block.page ?? "—"} 页
        <span className="h-px flex-1 bg-slate-200" />
      </div>
    );
  }
  if (block.type === "table") {
    return (
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <tbody>
            {(block.rows ?? []).map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  <td
                    key={cellIndex}
                    className="border border-slate-300 px-3 py-2 align-top leading-6"
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (block.type === "footnote") {
    return (
      <aside className="border-l-2 border-slate-300 pl-4 text-sm leading-7 text-slate-600">
        <span className="font-medium">脚注 {block.number ?? ""}</span>
        {block.text ? `　${block.text}` : ""}
      </aside>
    );
  }
  if (block.type === "heading") {
    const level = Math.min(Math.max(block.level ?? 2, 1), 4);
    const Heading = `h${level}` as "h1" | "h2" | "h3" | "h4";
    return (
      <Heading
        className={cn(
          "font-semibold leading-tight text-slate-950",
          level === 1 && "text-2xl",
          level === 2 && "pt-2 text-xl",
          level === 3 && "text-lg",
          level === 4 && "text-base"
        )}
      >
        {block.text}
      </Heading>
    );
  }
  return (
    <p className="whitespace-pre-wrap text-[15px] leading-8 text-slate-800">
      {block.text}
    </p>
  );
}

function ReaderState({
  text,
  tone = "neutral",
}: {
  text: string;
  tone?: "neutral" | "error";
}) {
  return (
    <Card>
      <CardContent
        className={cn(
          "p-8 text-center text-sm text-slate-500",
          tone === "error" && "text-red-700"
        )}
      >
        {text}
      </CardContent>
    </Card>
  );
}
