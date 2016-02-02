
all: reglementCoupeDeFrance.pdf

%.pdf: %.tex
	pdflatex $^
	#Twice for ToC
	pdflatex $^

clean:
	rm -rf *.aux *.out *.log *.pdf
