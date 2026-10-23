export const metadata = { title: "Contact · ri-layercake" };

export default function Contact() {
  return (
    <article className="doc contact">
      <h1>Contact</h1>
      <p className="lead">
        ri-layercake is built and maintained by Banu Munnangi. Questions, feedback, a paste that did not parse, or a
        structure you would like to see: get in touch.
      </p>
      <dl className="contact-card">
        <dt>Name</dt>
        <dd>Banu Munnangi</dd>
        <dt>Email</dt>
        <dd><a href="mailto:banu.munnangi@gmail.com">banu.munnangi@gmail.com</a></dd>
        <dt>Website</dt>
        <dd><a href="https://banumunnangi.com" rel="noopener noreferrer">banumunnangi.com</a></dd>
      </dl>
      <p className="muted">
        Please do not email real programme data. Replace figures with invented ones; the app itself never sends your
        data anywhere.
      </p>
    </article>
  );
}
