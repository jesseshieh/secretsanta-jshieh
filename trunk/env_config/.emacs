;; Jesse Shieh <jesses@google.com>

; TODO
; (load "hilit19")
; if after delete word, looking at a space, delete it
; if can't page down, move to the end
; specify the g4 diff program
; make start_igfe.sh emacs gdb friendly
; auto-insert comment characters
; function rolling
; quickly search the word under the cursor

(load "~/.emacs.defun" t t t)

(menu-bar-mode nil)
(tool-bar-mode nil)
(line-number-mode t)
(column-number-mode t)

;; Set up the keyboard so the delete key on both the regular keyboard
;; and the keypad delete the character under the cursor and to the right
;; under X, instead of the default, backspace behavior.
(global-set-key [delete] 'delete-char)
(global-set-key [kp-delete] 'delete-char)

;; turn on font-lock mode
(global-font-lock-mode t)

(setq mac-command-modifier 'control)
(setq mac-control-modifier 'meta)

(setq compilation-scroll-output t)
(setq compilation-window-height 8)

(setq compilation-finish-function 'kill-after-compilation)
(fset 'yes-or-no-p 'y-or-n-p)
;(setq display-time-day-and-date t) (display-time)
(require 'paren) (show-paren-mode t)
(setq-default indent-tabs-mode nil)
;(setq-default truncate-lines t)
;(require 'auto-show) (auto-show-mode 1) (setq-default auto-show-mode t)
;(auto-show-make-point-visible)
(setq query-replace-highlight t)
(setq search-highlight t)
;;(type-break-mode)
(follow-mode t)
(setq scroll-step 1)
(setq scroll-conservatively 5)
(setq kill-whole-line t)
(load-library "align")
(setq align-indent-before-aligning 't)
(global-auto-revert-mode 1)

;; The google style guidelines prescribe 80 characters.  But some people
;; find this hard to read, so I compromise a bit.
(setq-default fill-column 75)
(setq ring-bell-function (lambda ()))  ;; disable beeping
(setq inhibit-startup-message t)
(setq initial-scratch-message "")
; (setq tempo-interactive t)
(setq comment-column 2)

;; from http://wiki.corp.google.com/twiki/bin/view/Main/GnuEmacsBackupFiles
;; Put autosave files (ie #foo#) in one place, *not* scattered all over the
;; file system! (The make-autosave-file-name function is invoked to determine
;; the filename of an autosave file.)
(defvar autosave-dir "~/.emacs_autosave/")
(make-directory autosave-dir t)
(defun auto-save-file-name-p (filename)
    (string-match "^#.*#$" (file-name-nondirectory filename)))

(defun make-auto-save-file-name ()
    (concat autosave-dir
                      (if buffer-file-name
                                        (concat "#" (file-name-nondirectory buffer-file-name) "#")
                                    (expand-file-name (concat "#%" (buffer-name) "#")))))

;; Put backup files (ie foo~) in one place too. (The backup-directory-alist
;; list contains regexp=>directory mappings; filenames matching a regexp are
;; backed up in the corresponding directory. Emacs will mkdir it if necessary.)
(defvar backup-dir "~/.emacs_backup/")
(setq backup-directory-alist (list (cons "." backup-dir)))

;; Save Place
(require 'saveplace)
(setq-default save-place t)
(setq save-place-file (concat "/tmp/emacs-places-" (getenv "USER")))
(defun cpplint ()
  "Runs cpplint on the current buffer"
  (interactive)
  (compile
   (format "/home/build/google2/tools/cpplint.py %s 2>&1 | grep -v 'Line ends'"
	   buffer-file-name)))
; hooks
; dynamic changing of text in programming modes
(autoload 'camelCase-mode "/home/jesses/init/camelCase-mode" nil t)
(add-hook 'shell-mode-hook 'ansi-color-for-comint-mode-on)
(add-hook 'write-file-hooks 'delete-trailing-whitespace)
(add-hook 'c-mode-common-hook
  (lambda ()
    (add-hook 'after-change-functions 'my-editing-function nil t)
    (turn-on-auto-fill)
    ; (setq fill-column 80)
    ; (modify-syntax-entry ?_ "w")
    ; C-d doesn't seem to work in cc-mode, this fixes it
    (setq c-hungry-delete-key t)
    ;(setq c-auto-newline 1)
    (define-key c-mode-base-map "\C-d" 'backward-word)
    (tempo-use-tag-list 'c-tempo-tags)
    (tempo-use-tag-list 'c++-tempo-tags)
    ;(my-key-swap my-key-pairs)
    (camelCase-mode 1)
    ;; Tab
    ;;(global-set-key (kbd "TAB") 'tab-indent-or-complete)
    (define-key c-mode-base-map (kbd "TAB") 'tab-indent-or-complete)
    ))


;; un-breaking cut n' paste
;(setq x-select-enable-clipboard t)
;(setq interprogram-paste-function 'x-cut-buffer-or-selection-value)

;; enable visual feedback on selections
(setq-default transient-mark-mode t)

;; always end a file with a newline
(setq require-final-newline t)

;; stop at the end of the file, not just add lines
(setq next-line-add-newlines nil)

(when window-system
  ;; enable wheelmouse support by default
  (mwheel-install)
  ;; Colors
  (global-hl-line-mode t)
  ;; use extended compound-text coding for X clipboard
  (set-selection-coding-system 'compound-text-with-extensions))

;(load-file "~jesses/init/google.elc")
;(load-file "/home/build/public/google/util/google.el")
;(load-file "~jesses/init/google.el")
;(setq compile-command "make-dbg -r ")
;(setq gud-gdb-command-name "./start_igfe.sh")
;(setq compilation-read-command nil)
;(setq p3-use-p4config-exclusively t)
;(require 'g4)
;(require 'p4-google)              ;; g4-annotate, improves find-file-at-point
;(require 'compilation-colorization) ;; colorizes output of (i)grep
;(require 'googlemenu)               ;; handy Google menu bar
(global-unset-key "\C-u")

;; Navigation
(global-set-key "\C-h" 'next-line)
(global-set-key "\C-t" 'previous-line)
(global-set-key "\C-d" 'my-backward-word)
(global-set-key "\C-n" 'my-forward-word)
(global-set-key "\C-un" 'forward-word)
(global-set-key "\C-u\C-n" 'forward-word)
(global-set-key "\C-uh" 'forward-paragraph)
(global-set-key "\C-u\C-h" 'forward-paragraph)
(global-set-key "\C-ut" 'backward-paragraph)
(global-set-key "\C-u\C-t" 'backward-paragraph)
(global-set-key "\M-d" 'backward-char)
(global-set-key "\M-n" 'forward-char)
(global-set-key "\M-h" 'forward-paragraph)
(global-set-key "\M-t" 'backward-paragraph)
(global-set-key "\C-l" 'goto-line)
(global-set-key "\C-uwl" 'what-line)
(global-set-key "\C-f" 'scroll-up)
(global-set-key "\C-b" 'scroll-down)
(global-set-key (kbd "ESC <up>") 'static-scroll-up)
(global-set-key (kbd "ESC <down>") 'static-scroll-down)
(global-set-key "\C-o" 'beginning-of-code-line)
(global-set-key "\C-j" 'open-line-above)
(global-set-key "\C-ue" 'end-of-buffer)
(global-set-key "\C-u\C-e" 'end-of-buffer)
(global-set-key "\C-uo" 'beginning-of-buffer)
(global-set-key "\C-u\C-o" 'beginning-of-buffer)
(global-set-key [kp-divide] 'scroll-down-keep-cursor)
(global-set-key [kp-multiply] 'scroll-up-keep-cursor)
;(global-set-key [(return)] 'newline-and-indent)
;(global-set-key [(linefeed)] 'newline)

;; Deleting
;(global-set-key "\C-v" 'kill-word)
(global-set-key "\C-v" 'kill-source-code-word)
(global-set-key (kbd "ESC <backspace>") 'static-scroll-down)
;(global-set-key "\C-c" 'delete-char)
(global-set-key "\C-k" 'kill-entire-line-or-region)
(global-set-key "\C-uj" 'join-line)

;; Tempo
(global-set-key "\C-\\" 'tempo-complete-tag)
;(global-set-key "\C-\\" 'tempo-forward-mark)

;; Undo
(global-set-key "\C-z" 'undo)

;; Searching
;; Use C-s C-w to search for the word under the cursor
(global-set-key "\C-s" 'isearch-forward)
(global-set-key "\C-q" 'query-replace)
; (global-set-key "\M-q" 'replace-string)
;(global-set-key "\C-uh" 'isearch-repeat-forward)
;(global-set-key "\C-ut" 'isearch-repeat-backward)

;; Windows
(global-set-key "\C-u0" 'kill-buffer-delete-window)
;(global-set-key "\C-u0" 'kill-buffer)
(global-set-key "\C-u1" 'delete-other-windows)
(global-set-key "\C-u2" 'split-window-and-focus)
;jesses (global-set-key "\M-h" 'enlarge-window) jesses
;jesses (global-set-key "\M-t" 'shrink-window) jesses
(global-set-key "\C-u\C-b" 'list-buffers-and-focus)
(global-set-key "\C-ub" 'list-buffers-and-focus)
(global-set-key "\C-u\C-w" 'other-window)
(global-set-key "\C-uw" 'other-window)
(global-set-key "\C-u\C-k" 'kill-buffer)
(global-set-key "\C-uk" 'kill-buffer)

;; Exiting
(global-set-key "\C-us" 'save-buffer)
(global-set-key "\C-u\C-s" 'save-buffer)
(global-set-key "\C-u\C-c" 'save-buffers-kill-emacs)
(global-set-key "\C-uc" 'save-buffers-kill-emacs)
; (global-set-key "\C-u\C-h" 'shell)

;; Files
; (global-set-key "\C-l" 'speedbar)
(global-set-key "\C-uf" 'find-file)
(global-set-key "\C-u\C-f" 'find-file)
(global-set-key "\C-u\C-r" 'google-rotate-among-files)
(global-set-key "\C-ur" 'google-rotate-among-files)

;; Clipboard
(global-set-key "\C-p" 'yank)
;(global-set-key "\C-p" 'yank-or-yank-pop)
(global-set-key "\C-y" 'copy-region-as-kill)

;; Commenting
(global-set-key "\C-r" 'toggle-line-comment)
(global-set-key "\C-ud" 'prefix-region)
(global-set-key "\C-u\C-d" 'prefix-region)

;; Macros
(global-set-key "\C-u[" 'start-kbd-macro)
(global-set-key "\C-u]" 'end-kbd-macro)
(global-set-key "\C-um" 'call-last-kbd-macro)
(global-set-key "\C-u\C-m" 'call-last-kbd-macro)

;; Function keys
(global-set-key [f1] 'my-compile)
(global-set-key [f2] 'previous-error)
(global-set-key [f3] 'next-error)
(global-set-key [f4] 'google-pop-tag)
(global-set-key [f5] 'bubble-buffer)
(global-set-key [f6] 'gdb)
(global-set-key [f12] 'my-delete-other-windows)

;; Google commands
(global-set-key "\C-ugc" 'my-compile)
(global-set-key "\C-ugt" 'google-find-tag-and-focus)
(global-set-key "\C-ugs" 'google-show-callers)

;; p4
(global-set-key "\C-uge" 'p4-edit)
(global-set-key "\C-ugr" 'p4-revert)

;; make home and end keys work in grhat xterm emulators.
;; neither portable nor guaranteed to work.
(unless window-system
    (global-set-key "\eOH" 'beginning-of-line)
    (global-set-key "\eOF" 'end-of-line))
(global-set-key "\C-m" 'newline-and-indent)

;; Xrefactory configuration part ;;
;; some Xrefactory defaults can be set here
;(defvar xref-current-project nil) ;; can be also "my_project_name"
;(defvar xref-key-binding 'global) ;; can be also 'local or 'none
;(setq load-path (cons "/home/build/public/eng/elisp/xref/emacs" load-path))
;(setq exec-path (cons "/home/build/public/eng/elisp/xref" exec-path))
;(load "xrefactory")
;; end of Xrefactory configuration part ;;
;(message "xrefactory loaded")

;(setq default-mode-line-format
;      (list "-- "
;            "%b:"
;            "%l"
;            "\tC%c"
;            ))

(put 'downcase-region 'disabled nil)

;; set auto-mode by file type
;(require 'hilit19)
;(autoload 'javascript-mode "/home/jesses/init/javascript-mode" nil t)
;(autoload 'html-helper-mode "/home/jesses/init/html-helper-mode" "Yay HTML" t)
(setq javascript-indentation 2)
(setq auto-mode-alist (cons  '("\\.defun$" . emacs-lisp-mode) auto-mode-alist))
(setq auto-mode-alist (cons  '("BUILD$" . c-mode) auto-mode-alist))
;(setq auto-mode-alist (cons '("\\.tpl$" . html-helper-mode) auto-mode-alist))
;(setq auto-mode-alist (cons '("\\.html$" . html-helper-mode) auto-mode-alist))
;(setq auto-mode-alist (cons  '("\\.js$" . javascript-mode) auto-mode-alist))

