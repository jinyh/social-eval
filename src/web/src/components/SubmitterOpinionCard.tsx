import { FileText } from "lucide-react";

import type { SubmitterOpinion } from "@/lib/types";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";

type SubmitterOpinionCardProps = {
  opinion: SubmitterOpinion;
};

export function SubmitterOpinionCard({ opinion }: SubmitterOpinionCardProps) {
  if (!opinion.ready) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>预审意见</CardTitle>
          <CardDescription>综合意见生成后在此展示，无需等待编辑。</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-500">综合意见尚未生成，请稍后刷新查看。</p>
        </CardContent>
      </Card>
    );
  }

  const suggestions = opinion.modification_suggestions.length
    ? opinion.modification_suggestions
    : [];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <div className="rounded-xl border border-blue-100 bg-blue-50 p-2 text-blue-700">
            <FileText className="h-5 w-5" />
          </div>
          <div>
            <CardTitle>预审意见</CardTitle>
            <CardDescription>基于多轮评审与交叉复核的智能辅助综合意见，供改进论文参考。</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <section>
          <h3 className="text-sm font-semibold text-slate-950">综合意见</h3>
          <p className="mt-2 whitespace-pre-line text-sm leading-7 text-slate-700">
            {opinion.synthesis || "暂无综合意见。"}
          </p>
        </section>
        <section>
          <h3 className="text-sm font-semibold text-slate-950">修改建议</h3>
          {suggestions.length ? (
            <ul className="mt-2 space-y-2">
              {suggestions.map((item, index) => (
                <li
                  key={index}
                  className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-700"
                >
                  {index + 1}. {item}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-slate-500">暂无修改建议。</p>
          )}
        </section>
      </CardContent>
    </Card>
  );
}
