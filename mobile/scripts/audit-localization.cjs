const ts = require('typescript');
const fs = require('fs');
const path = require('path');
function files(dir) { return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => e.isDirectory() ? files(path.join(dir, e.name)) : /\.tsx$/.test(e.name) ? [path.join(dir, e.name)] : []); }
const findings = [];
const allowed = new Set(['Dabbarha', 'DABBARHA', 'English', 'العربية', 'YYYY-MM-DD', 'user@example.com']);
for (const file of [...files('app'), ...files('src/components'), ...files('src/providers')]) {
  const source = fs.readFileSync(file, 'utf8');
  if (/\uFFFD|Ã|Â|â€|Ø|Ù/.test(source)) findings.push(`${file}: possible corrupted encoding`);
  const ast = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true);
  function visit(node) {
    const uiAttribute = ts.isStringLiteral(node) && ts.isJsxAttribute(node.parent) && /^(title|label|placeholder|helperText|accessibilityLabel|accessibilityHint|message)$/.test(node.parent.name.getText(ast));
    if (ts.isJsxText(node) || uiAttribute || ts.isTemplateExpression(node)) {
      const value = ts.isTemplateExpression(node) ? node.getText(ast) : node.text.trim();
      if (/[A-Za-z]/.test(value) && !allowed.has(value) && !(ts.isTemplateExpression(node) && !/[A-Za-z]{2}/.test(node.head.text + node.templateSpans.map(s => s.literal.text).join('')))) {
        // Non-display identifiers generated for local chat messages.
        if (file.endsWith('chat.tsx') && value.includes('Math.random()')) return;
        findings.push(`${file}:${ast.getLineAndCharacterOfPosition(node.getStart()).line + 1}: ${value}`);
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(ast);
}
console.log(findings.length ? findings.join('\n') : 'No untranslated literal JSX copy, UI attributes, or prose templates found.');
process.exitCode = findings.length ? 1 : 0;
