const text = `Generate the certificates.<br>Drop the csv file`;
const speed = 50; // milliseconds per character
let index = 0;

function type() {
  const element = document.getElementById("tagline");
  if (index < text.length) {
    if (text.charAt(index) === '<' && text.substring(index, index + 4) === '<br>') {
      element.innerHTML += '<br>';
      index += 4;
    } else {
      element.innerHTML += text.charAt(index);
      index++;
    }
    setTimeout(type, speed);
  } else {
    // Optional: Add a blinking cursor effect after typing is done
    element.style.borderRight = '2px solid transparent';
  }
}

window.onload = type;