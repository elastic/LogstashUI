// Simple mode for highlighting comments in config files
// Lines starting with # are treated as comments

(function(mod) {
  if (typeof exports == "object" && typeof module == "object") // CommonJS
    mod(require("../../lib/codemirror"));
  else if (typeof define == "function" && define.amd) // AMD
    define(["../../lib/codemirror"], mod);
  else // Plain browser env
    mod(CodeMirror);
})(function(CodeMirror) {
"use strict";

CodeMirror.defineMode("simplecomment", function() {
  return {
    token: function(stream, state) {
      // Check if line starts with # (after optional whitespace)
      if (stream.sol() && stream.match(/^\s*#/)) {
        stream.skipToEnd();
        return "comment";
      }
      
      // If we're already in a comment line, continue
      if (state.commentLine) {
        stream.skipToEnd();
        return "comment";
      }
      
      // Check if current position starts a comment
      if (stream.match(/^\s*#/)) {
        stream.skipToEnd();
        return "comment";
      }
      
      // Otherwise, advance one character
      stream.next();
      return null;
    },
    startState: function() {
      return {
        commentLine: false
      };
    },
    lineComment: "#"
  };
});

CodeMirror.defineMIME("text/x-simplecomment", "simplecomment");

});
