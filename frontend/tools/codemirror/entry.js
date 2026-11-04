// The parts of CodeMirror 6 KlippEye's editor uses (frontend/src/app/51-config-editor.js), exported as the global CM.
export { EditorState, EditorSelection, Compartment, StateEffect, StateField, Prec } from "@codemirror/state";
export { EditorView, keymap, lineNumbers, highlightActiveLine, highlightActiveLineGutter, drawSelection, highlightSpecialChars, rectangularSelection, crosshairCursor, dropCursor, Decoration, ViewPlugin, placeholder } from "@codemirror/view";
export { defaultKeymap, history, historyKeymap, indentWithTab, undo, redo, undoDepth, redoDepth, toggleLineComment, selectAll } from "@codemirror/commands";
export { StreamLanguage, syntaxHighlighting, HighlightStyle, foldGutter, foldKeymap, foldService, codeFolding, foldAll, unfoldAll, indentOnInput, bracketMatching, indentUnit } from "@codemirror/language";
export { search, searchKeymap, highlightSelectionMatches, openSearchPanel, closeSearchPanel, SearchQuery, setSearchQuery, findNext, findPrevious, replaceNext, replaceAll, getSearchQuery } from "@codemirror/search";
export { closeBrackets, closeBracketsKeymap } from "@codemirror/autocomplete";
export { tags } from "@lezer/highlight";
