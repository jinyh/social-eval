import type { InternalDimensionScore } from "@/lib/types";
import { anonymizeModelScores, formatScore } from "@/lib/report";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";

type ModelComparisonTableProps = {
  dimension: InternalDimensionScore;
};

export function ModelComparisonTable({ dimension }: ModelComparisonTableProps) {
  const scores = anonymizeModelScores(dimension.ai?.model_scores);

  return (
    <Table>
      <TableHeader>
        <TableRow>
          {scores.map((score) => (
            <TableHead key={score.label} className="text-center">
              {score.label}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        <TableRow>
          {scores.map((score) => (
            <TableCell key={score.label} className="text-center text-base font-semibold text-slate-950">
              {score.score === null ? "--" : `${formatScore(score.score)}分`}
            </TableCell>
          ))}
        </TableRow>
      </TableBody>
    </Table>
  );
}
