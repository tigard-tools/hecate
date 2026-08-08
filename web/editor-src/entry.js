// Entry point for the vendored CodeMirror bundle.
//
// esbuild bundles this into ../vendor/codemirror.js (a single, self-contained
// ES module) so the web console can `import` a real editor without a build
// step or any network access at runtime. Rebuild with `npm run build` after
// bumping a dependency. See ../README.md.

import { EditorView, basicSetup } from "codemirror";
import { EditorState, Compartment } from "@codemirror/state";
import { keymap, placeholder } from "@codemirror/view";
import { indentWithTab } from "@codemirror/commands";
import { python } from "@codemirror/lang-python";
import { oneDark } from "@codemirror/theme-one-dark";

export {
  EditorView,
  EditorState,
  Compartment,
  basicSetup,
  keymap,
  placeholder,
  indentWithTab,
  python,
  oneDark,
};
