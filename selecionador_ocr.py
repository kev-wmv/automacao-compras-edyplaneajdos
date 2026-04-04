import sys
import tkinter as tk
from tkinter import filedialog

try:
    import pdfplumber
    from PIL import ImageTk
except ImportError:
    print("ERRO: Dependências não encontradas.")
    print("Execute: pip install pdfplumber Pillow")
    sys.exit(1)

class VisualCropSelector:
    def __init__(self, root, pdf_path):
        self.root = root
        self.pdf_path = pdf_path
        # 144 de resolução significa zoom de 2x em relação ao padrão (72dpi),
        # garantindo uma leitura melhor na tela.
        self.resolution = 144
        self.scale = self.resolution / 72.0
        
        root.title("Seletor Visual de Coordenadas OCR (pdfplumber)")
        root.geometry("1000x800")
        
        # Criação de containers para Scrollbar
        self.frame = tk.Frame(root)
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.frame, cursor="cross")
        self.hbar = tk.Scrollbar(self.frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.vbar = tk.Scrollbar(self.frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.config(xscrollcommand=self.hbar.set, yscrollcommand=self.vbar.set)
        
        self.hbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Abrir PDF e converter página 0 para imagem
        print(f"Abrindo {self.pdf_path} (Aguarde a renderização da imagem...)")
        self.pdf = pdfplumber.open(self.pdf_path)
        
        if len(self.pdf.pages) == 0:
            print("O PDF não possui páginas.")
            sys.exit(1)
            
        self.page = self.pdf.pages[0]
        self.pdf_image = self.page.to_image(resolution=self.resolution).original
            
        self.tk_im = ImageTk.PhotoImage(self.pdf_image)
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_im)
        self.canvas.config(scrollregion=self.canvas.bbox(tk.ALL))
        
        self.rect = None
        self.start_x = None
        self.start_y = None
        
        # Eventos do mouse para desenhar retângulo
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        
        # Instruções na interface
        tk.Label(root, text="Clique e arraste sobre a imagem para selecionar uma área. As coordenadas serão mostradas no terminal.", 
                 bg="#333", fg="white", font=("Arial", 11)).pack(fill=tk.X)
                 
        print("\nPronto! Arraste o mouse sobre a imagem da janela para selecionar uma área.")
        
    def on_press(self, event):
        # Mapeia coordenadas do clique para dentro do canvas com scroll
        self.start_x = self.canvas.canvasx(event.x)
        self.start_y = self.canvas.canvasy(event.y)
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline="red", width=2)
        
    def on_drag(self, event):
        cur_x = self.canvas.canvasx(event.x)
        cur_y = self.canvas.canvasy(event.y)
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)
        
    def on_release(self, event):
        end_x = self.canvas.canvasx(event.x)
        end_y = self.canvas.canvasy(event.y)
        
        # Converte pixels da interface gráfica diretamente para pontos PDF de volta (72dpi eq.)
        x0 = min(self.start_x, end_x) / self.scale
        top = min(self.start_y, end_y) / self.scale
        x1 = max(self.start_x, end_x) / self.scale
        bottom = max(self.start_y, end_y) / self.scale
        
        x0, top, x1, bottom = round(x0, 2), round(top, 2), round(x1, 2), round(bottom, 2)
        
        print("\n=======================================================")
        print(f"Coordenadas: [{x0}, {top}, {x1}, {bottom}]")
        
        try:
            # Testa automaticamente o que o pdfplumber lê usando as coordenadas geradas
            cropped = self.page.crop((x0, top, x1, bottom))
            text = cropped.extract_text()
            if text:
                # Limpa e apresenta o texto detectado tal como na extração real
                text_limpo = " ".join(text.split()).upper()
                print(f"Texto extraído: '{text_limpo}'")
            else:
                print("Texto extraído: (nenhum texto detectado)")
        except ValueError as e:
            print(f"Aviso - seleção muito pequena ou inválida: {e}")
        print("=======================================================\n")

def main():
    root = tk.Tk()
    root.withdraw()
    pdf_path = filedialog.askopenfilename(title="Selecione o PDF do contrato", filetypes=[("PDF", "*.pdf")])
    if not pdf_path:
        print("Nenhum arquivo selecionado.")
        sys.exit(0)
        
    root.deiconify()
    app = VisualCropSelector(root, pdf_path)
    
    # Ao fechar a janela, encerra os recursos do PDF corretamente
    def on_closing():
        if hasattr(app, 'pdf'):
            app.pdf.close()
        root.destroy()
        
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
